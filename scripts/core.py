import logging
import shutil
import tempfile
from pathlib import Path

from scripts import MANIFEST_NAME, SCRIPT_DIR, reporting
from scripts.git_helpers import git, is_series_patch_in_repo
from scripts.manifest import mark_unreached, run_manifest_series, run_patch_on_repo
from scripts.state import cleanup_worktree, record_base

logger = logging.getLogger("fuck-bpf")


def list_patch_dirs() -> list[str]:
    dirs: set[str] = set()
    for p in SCRIPT_DIR.rglob("*.patch"):
        dirs.add(p.parent.relative_to(SCRIPT_DIR).as_posix())
    for p in SCRIPT_DIR.rglob(".fuck-bpf-series"):
        dirs.add(p.parent.relative_to(SCRIPT_DIR).as_posix())
    return sorted(dirs)


def run_glob_series(series_dir: str, repo_dir: str, mode: str) -> bool:
    patches = sorted((SCRIPT_DIR / series_dir).glob("*.patch"))
    for i, patch in enumerate(patches):
        if not run_patch_on_repo(series_dir, repo_dir, patch.name, mode):
            if mode == "apply":
                # Bailing on the first failure means every later patch in the
                # series never ran. Name them, rather than letting the series
                # look like it simply had nothing left to do. Only meaningful
                # for a real apply: a dry-run scratch worktree and a probe
                # worktree both "fail" for reasons that say nothing about the
                # real tree, so reporting them there is noise, not signal.
                for skipped_over in patches[i + 1 :]:
                    mark_unreached(f"{series_dir}/{skipped_over.name}")
            return False
    return True


def run_series_steps(series_dir: str, repo_dir: str, mode: str) -> bool:
    # A series is defined by its manifest when it has one. Falling through to
    # the glob on a manifest *failure* re-ran every patch in the series, which
    # double-applied patches and reported already-applied ones as drops.
    if (SCRIPT_DIR / series_dir / MANIFEST_NAME).exists():
        return run_manifest_series(series_dir, repo_dir, mode)
    return run_glob_series(series_dir, repo_dir, mode)


def apply_series(series_dir: str) -> None:
    record_base(series_dir)
    run_series_steps(series_dir, str(Path.cwd() / series_dir), "apply")


def dry_run_series(series_dir: str) -> bool:
    tmpdir = Path(tempfile.mkdtemp(prefix="fuck-bpf-dry-run-"))
    target_repo = Path.cwd() / series_dir
    try:
        git("worktree", "add", str(tmpdir), "HEAD", cwd=target_repo, capture=False)
        result = run_series_steps(series_dir, str(tmpdir), "dry-run")
        if not result:
            git("am", "--abort", cwd=tmpdir, check=False, capture=False)
        return result
    finally:
        git("worktree", "remove", "--force", str(tmpdir), cwd=target_repo, check=False, capture=False)
        if tmpdir.exists():
            shutil.rmtree(tmpdir, ignore_errors=True)


def verify_series(series_dir: str) -> int:
    repo = Path.cwd() / series_dir
    reporting.header(series_dir)

    status = git("status", "--short", cwd=repo).stdout.strip()
    if status:
        logger.error("working tree not clean")
        return 1

    result = git("rev-parse", "--quiet", "--verify", "REBASE_HEAD", cwd=repo, check=False)
    if result.returncode == 0:
        logger.error("git am still in progress")
        return 1
    logger.info("git am clean")
    return 0


def cleanup_series_fallback(series_dir: str) -> None:
    repo = Path.cwd() / series_dir
    logger.info("Using fallback cleanup for %s", series_dir)
    git("am", "--abort", cwd=repo, check=False, capture=False)

    matched = 0
    while True:
        head = git("rev-parse", "HEAD", cwd=repo).stdout.strip()
        if not is_series_patch_in_repo(str(repo), series_dir, head):
            break
        matched += 1
        git("reset", "--hard", "HEAD~1", cwd=repo, check=False, capture=False)

    if matched == 0:
        revs = git("rev-list", "--max-count=50", "HEAD", cwd=repo).stdout.strip().split()
        for commit in revs:
            if is_series_patch_in_repo(str(repo), series_dir, commit):
                logger.error("refusing cleanup for %s: non-patch commit above applied patch", series_dir)
                return
    cleanup_worktree(series_dir)
