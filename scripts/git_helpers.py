import subprocess
from functools import cache
from pathlib import Path

from scripts import SCRIPT_DIR


def git(
    *args: str,
    cwd: Path | None = None,
    check: bool = True,
    capture: bool = True,
    input_text: str | None = None,
) -> subprocess.CompletedProcess:
    cmd = ["git"] + list(args)
    kwargs: dict = {}
    if cwd:
        kwargs["cwd"] = str(cwd)
    if capture:
        kwargs["capture_output"] = True
        kwargs["text"] = True
    if input_text is not None:
        kwargs["input"] = input_text
    result = subprocess.run(cmd, **kwargs)
    if check and result.returncode != 0:
        err = result.stderr.strip() if result.stderr else "unknown error"
        raise RuntimeError(f"git {' '.join(args)} failed: {err}")
    return result


def patch_id_for_file(patch: Path) -> str | None:
    result = git("patch-id", "--stable", cwd=Path.cwd(), capture=True, check=False, input_text=patch.read_text())
    if result.returncode != 0:
        return None
    return result.stdout.strip().split()[0] if result.stdout.strip() else None


@cache
def patch_id_for_commit(repo_dir: str, commit: str) -> str | None:
    cmd = ["git", "show", "--format=", commit]
    result = subprocess.run(cmd, cwd=Path.cwd() / repo_dir, capture_output=True, check=False)
    if result.returncode != 0:
        return None
    pid = subprocess.run(
        ["git", "patch-id", "--stable"],
        cwd=Path.cwd(),
        capture_output=True,
        input=result.stdout,
        check=False,
    )
    if pid.returncode != 0:
        return None
    return pid.stdout.decode(errors="replace").strip().split()[0] if pid.stdout.strip() else None


def is_patch_in_commit(repo_dir: str, patch: Path, commit: str) -> bool:
    commit_pid = patch_id_for_commit(repo_dir, commit)
    patch_pid = patch_id_for_file(patch)
    return bool(commit_pid and patch_pid and commit_pid == patch_pid)


def is_series_patch_in_repo(repo_dir: str, series_dir: str, commit: str) -> bool:
    for patch in sorted((SCRIPT_DIR / series_dir).glob("*.patch")):
        if is_patch_in_commit(repo_dir, patch, commit):
            return True
    return False


def is_patch_applied(repo_dir: str, patch: Path, series_dir: str) -> bool:
    result = git("apply", "--reverse", "--check", str(patch), cwd=Path.cwd() / repo_dir, capture=True, check=False)
    if result.returncode == 0:
        return True
    revs_result = git("rev-list", "--max-count=200", "HEAD", cwd=Path.cwd() / repo_dir, capture=True, check=False)
    if revs_result.returncode != 0:
        return False
    # Scan for an exact patch-id match first, then decide. Walking from HEAD
    # and bailing out on the first foreign commit rejects a patch that *is*
    # present whenever a later commit touches the same files, or whenever a
    # series commit no longer reproduces its patch-id byte-for-byte (an edited
    # patch file, a rebased or reformatted commit). In both cases the patch is
    # already in the tree and must not be applied a second time.
    for commit in revs_result.stdout.strip().split():
        if is_patch_in_commit(repo_dir, patch, commit):
            return True
    return False
