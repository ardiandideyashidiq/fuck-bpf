import logging
import shutil
import sys
import tempfile
from pathlib import Path

from scripts import MANIFEST_NAME, SCRIPT_DIR
from scripts.git_helpers import git, is_patch_applied

logger = logging.getLogger("fuck-bpf")

FAILED_PATCHES: list[str] = []

SERIES_STATS: dict[str, dict[str, int]] = {}


def reset_results() -> None:
    FAILED_PATCHES.clear()
    SERIES_STATS.clear()


def record_patch_result(series_dir: str, status: str) -> None:
    if series_dir not in SERIES_STATS:
        SERIES_STATS[series_dir] = {"applied": 0, "skipped": 0, "failed": 0}
    SERIES_STATS[series_dir][status] += 1


def mark_failed(patch_rel: str) -> None:
    FAILED_PATCHES.append(patch_rel)


def print_failures() -> int:
    if not FAILED_PATCHES:
        return 0
    logger.warning("Patches needing regeneration:")
    for p in FAILED_PATCHES:
        logger.warning("  Patch needs regeneration: %s", p)
    return 0


def print_summary() -> None:
    if not SERIES_STATS:
        return
    print(file=sys.stderr)
    print("Summary", file=sys.stderr)
    print("\u2500" * 48, file=sys.stderr)
    print(f"{'Series':<25} {'Applied':>8} {'Skipped':>8} {'Failed':>8}", file=sys.stderr)
    t_a = t_s = t_f = 0
    for sdir, stats in sorted(SERIES_STATS.items()):
        a, s, f = stats["applied"], stats["skipped"], stats["failed"]
        t_a += a
        t_s += s
        t_f += f
        print(f"{sdir:<25} {a:>8} {s:>8} {f:>8}", file=sys.stderr)
    print("\u2500" * 48, file=sys.stderr)
    print(f"{'Total':<25} {t_a:>8} {t_s:>8} {t_f:>8}", file=sys.stderr)


def trim_manifest_line(line: str) -> str:
    return line.split("#")[0].strip()


def run_patch_on_repo(series_dir: str, repo_dir: str, patch_name: str, mode: str) -> bool:
    patch = SCRIPT_DIR / series_dir / patch_name
    patch_rel = f"{series_dir}/{patch_name}"

    if not patch.exists():
        mark_failed(patch_rel)
        if mode != "probe":
            record_patch_result(series_dir, "failed")
        return False

    if is_patch_applied(repo_dir, patch, series_dir):
        if mode != "probe":
            logger.info("Skipping duplicate patch: %s", patch_rel)
            record_patch_result(series_dir, "skipped")
        return True

    result = git("am", "-3", str(patch), cwd=Path(repo_dir), check=False, capture=False)
    if result.returncode == 0:
        if mode == "apply":
            logger.info("Applied patch: %s", patch_rel)
        elif mode == "dry-run":
            logger.info("Would apply patch: %s", patch_rel)
        if mode != "probe":
            record_patch_result(series_dir, "applied")
        return True

    git("am", "--abort", cwd=Path(repo_dir), check=False, capture=False)
    if mode != "probe":
        mark_failed(patch_rel)
        record_patch_result(series_dir, "failed")
    return False


def run_patch_sequence(series_dir: str, repo_dir: str, mode: str, *patch_names: str) -> bool:
    for pn in patch_names:
        if not run_patch_on_repo(series_dir, repo_dir, pn, mode):
            return False
    return True


def probe_option(series_dir: str, repo_dir: str, *patch_names: str) -> bool:
    tmpdir = Path(tempfile.mkdtemp(prefix="fuck-bpf-option-"))
    try:
        git("worktree", "add", str(tmpdir), "HEAD", cwd=Path(repo_dir), capture=False)
        result = run_patch_sequence(series_dir, str(tmpdir), "probe", *patch_names)
        if not result:
            git("am", "--abort", cwd=tmpdir, check=False, capture=False)
        return result
    finally:
        git("worktree", "remove", "--force", str(tmpdir), cwd=Path(repo_dir), check=False, capture=False)
        if tmpdir.exists():
            shutil.rmtree(tmpdir, ignore_errors=True)


def run_patch_choice(series_dir: str, repo_dir: str, mode: str, choice_name: str, *options: str) -> bool:
    for opt_line in options:
        parts = opt_line.strip().split()
        opt_name = parts[0]
        opt_patches = parts[1:]
        if probe_option(series_dir, repo_dir, *opt_patches):
            logger.info("Selected patch option: %s %s %s", series_dir, choice_name, opt_name)
            return run_patch_sequence(series_dir, repo_dir, mode, *opt_patches)
    mark_failed(f"{series_dir}/{choice_name}")
    return False


def run_manifest_series(series_dir: str, repo_dir: str, mode: str) -> bool:
    manifest = SCRIPT_DIR / series_dir / MANIFEST_NAME
    if not manifest.exists():
        return False

    lines = manifest.read_text().splitlines()
    in_choice = False
    choice_name = ""
    options: list[str] = []
    i = 0
    while i < len(lines):
        line = trim_manifest_line(lines[i])
        i += 1
        if not line:
            continue

        keyword = line.split()[0] if line.split() else ""

        if in_choice:
            if keyword == "option":
                options.append(line[len("option ") :])
                continue
            if keyword == "endchoice":
                if not run_patch_choice(series_dir, repo_dir, mode, choice_name, *options):
                    return False
                in_choice = False
                choice_name = ""
                options = []
                continue
            logger.error("Invalid manifest line in choice %s: %s", manifest, line)
            return False

        if keyword == "patch":
            pn = line[len("patch ") :].strip()
            if not run_patch_on_repo(series_dir, repo_dir, pn, mode):
                return False
        elif keyword == "choice":
            in_choice = True
            choice_name = line[len("choice ") :].strip()
            options = []
        else:
            logger.error("Invalid manifest line in %s: %s", manifest, line)
            return False

    if in_choice:
        logger.error("Unclosed choice in %s: %s", manifest, choice_name)
        return False
    return True
