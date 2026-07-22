import logging
import shutil
import tempfile
from pathlib import Path

from rich.console import Console
from rich.table import Table

from scripts import MANIFEST_NAME, SCRIPT_DIR
from scripts.git_helpers import git, is_patch_applied

logger = logging.getLogger("fuck-bpf")
_console = Console(stderr=True, highlight=False)

FAILED_PATCHES: list[str] = []
NOT_NEEDED_PATCHES: list[str] = []

SERIES_STATS: dict[str, dict[str, int]] = {}


def reset_results() -> None:
    FAILED_PATCHES.clear()
    NOT_NEEDED_PATCHES.clear()
    SERIES_STATS.clear()


def record_patch_result(series_dir: str, status: str) -> None:
    if series_dir not in SERIES_STATS:
        SERIES_STATS[series_dir] = {"applied": 0, "skipped": 0, "failed": 0, "not_needed": 0}
    SERIES_STATS[series_dir][status] += 1


def mark_failed(patch_rel: str) -> None:
    FAILED_PATCHES.append(patch_rel)


def mark_not_needed(patch_rel: str) -> None:
    NOT_NEEDED_PATCHES.append(patch_rel)


def _patch_added_lines_present(repo_dir: str, patch: Path) -> bool:
    try:
        text = patch.read_text()
    except OSError:
        return False
    current_file = None
    added: dict[str, list[str]] = {}
    for line in text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
            added.setdefault(current_file, [])
        elif line.startswith("+") and not line.startswith("+++") and current_file:
            added[current_file].append(line[1:])
    for filepath, lines in added.items():
        target = Path(repo_dir) / filepath
        if not target.exists():
            return False
        try:
            content = target.read_text()
        except OSError:
            return False
        for added_line in lines:
            if added_line not in content:
                return False
    return True


def print_failures() -> int:
    showed = False
    if NOT_NEEDED_PATCHES:
        if not showed:
            _console.print()
        _console.print("[bold cyan]Patches not needed for this AOSP version:[/]")
        for p in NOT_NEEDED_PATCHES:
            _console.print(f"  [cyan]\u26A0[/] {p}")
        showed = True
    if FAILED_PATCHES:
        if not showed:
            _console.print()
        _console.print("[bold yellow]Patches needing regeneration:[/]")
        for p in FAILED_PATCHES:
            _console.print(f"  [red]\u2717[/] {p}")
        showed = True
    return 0


def print_summary() -> None:
    if not SERIES_STATS:
        return
    _console.print()
    table = Table(title="Patch Series Summary")
    table.add_column("Series", style="cyan")
    table.add_column("Applied", justify="right", style="green")
    table.add_column("Skipped", justify="right", style="yellow")
    table.add_column("Not Needed", justify="right", style="cyan")
    table.add_column("Failed", justify="right", style="red")
    t_a = t_s = t_n = t_f = 0
    for sdir, stats in sorted(SERIES_STATS.items()):
        a = stats.get("applied", 0)
        s = stats.get("skipped", 0)
        n = stats.get("not_needed", 0)
        f = stats.get("failed", 0)
        t_a += a
        t_s += s
        t_n += n
        t_f += f
        table.add_row(sdir, str(a), str(s), str(n), str(f))
    table.add_row("Total", str(t_a), str(t_s), str(t_n), str(t_f), style="bold")
    _console.print(table)


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
        check = git("apply", "--check", str(patch), cwd=Path(repo_dir), capture=True, check=False)
        not_needed = False
        if check.returncode != 0 and "already exists in working directory" in check.stderr:
            not_needed = True
        else:
            rev = git("apply", "--reverse", "--check", "-3", str(patch), cwd=Path(repo_dir), capture=True, check=False)
            if rev.returncode == 0:
                not_needed = True
            else:
                not_needed = _patch_added_lines_present(repo_dir, patch)
        if not_needed:
            mark_not_needed(patch_rel)
            record_patch_result(series_dir, "not_needed")
        else:
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
