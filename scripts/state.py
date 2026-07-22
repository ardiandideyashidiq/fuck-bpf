import json
import logging
from pathlib import Path

from scripts import STATE_FILENAME
from scripts.git_helpers import git

logger = logging.getLogger("fuck-bpf")


def state_path() -> Path:
    return Path.cwd() / STATE_FILENAME


def has_series(series_dir: str) -> bool:
    sp = state_path()
    if not sp.exists():
        return False
    data = json.loads(sp.read_text())
    return series_dir in data.get("series", {})


def record_base(series_dir: str) -> None:
    if has_series(series_dir):
        return
    sp = state_path()
    data = {}
    if sp.exists():
        data = json.loads(sp.read_text())
    if "series" not in data:
        data["series"] = {}
    head = git("rev-parse", "HEAD", cwd=Path.cwd() / series_dir).stdout.strip()
    data["series"][series_dir] = head
    sp.write_text(json.dumps(data, indent=2) + "\n")


def cleanup_worktree(series_dir: str, reset_target: str = "HEAD") -> None:
    repo = Path.cwd() / series_dir
    logger.info("Cleaning %s to %s", series_dir, reset_target)
    git("am", "--abort", cwd=repo, check=False, capture=False)
    git("reset", "--hard", reset_target, cwd=repo, check=False, capture=False)
    git("clean", "-ffdx", cwd=repo, check=False, capture=False)


def cleanup_to_base(series_dir: str, base: str) -> bool:
    repo = Path.cwd() / series_dir
    result = git("cat-file", "-e", f"{base}^{{commit}}", cwd=repo, check=False)
    if result.returncode != 0:
        logger.error("cleanup base commit missing for %s: %s", series_dir, base)
        return False
    cleanup_worktree(series_dir, base)
    return True


def cleanup_from_state() -> int:
    sp = state_path()
    if not sp.exists():
        return 0
    data = json.loads(sp.read_text())
    exit_code = 0
    for series_dir, base in data.get("series", {}).items():
        logger.info("Using recorded cleanup state for %s", series_dir)
        if not cleanup_to_base(series_dir, base):
            exit_code = 1
    if exit_code == 0:
        sp.unlink(missing_ok=True)
    return exit_code
