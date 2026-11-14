import logging
import shutil
import tempfile
from pathlib import Path

from scripts import MANIFEST_NAME, SCRIPT_DIR, reporting
from scripts.git_helpers import git, is_patch_applied

logger = logging.getLogger("fuck-bpf")

FAILED_PATCHES: list[str] = []
NOT_NEEDED_PATCHES: list[str] = []
SKIPPED_PATCHES: list[str] = []

# Patches that a series never got to (a sequence stopped at an earlier failure,
# or a choice picked another option). They were never applied and must be
# reported, otherwise a broken series looks like a clean run.
UNREACHED_PATCHES: list[str] = []

SERIES_STATS: dict[str, dict[str, int]] = {}
# Every patch the run actually considered, in order, with its outcome. The
# counts in SERIES_STATS cannot distinguish "already applied" from "never
# applied", which is exactly how patches went missing silently.
PATCH_OUTCOMES: dict[str, str] = {}


def reset_results() -> None:
    FAILED_PATCHES.clear()
    NOT_NEEDED_PATCHES.clear()
    SKIPPED_PATCHES.clear()
    UNREACHED_PATCHES.clear()
    SERIES_STATS.clear()
    PATCH_OUTCOMES.clear()


def record_patch_result(series_dir: str, status: str, patch_rel: str | None = None) -> None:
    if series_dir not in SERIES_STATS:
        SERIES_STATS[series_dir] = {"applied": 0, "skipped": 0, "failed": 0, "not_needed": 0}
    SERIES_STATS[series_dir][status] += 1
    if patch_rel is not None:
        PATCH_OUTCOMES[patch_rel] = status


def mark_failed(patch_rel: str) -> None:
    FAILED_PATCHES.append(patch_rel)


def mark_not_needed(patch_rel: str) -> None:
    NOT_NEEDED_PATCHES.append(patch_rel)


def mark_skipped(patch_rel: str) -> None:
    SKIPPED_PATCHES.append(patch_rel)


def mark_unreached(patch_rel: str) -> None:
    if patch_rel not in UNREACHED_PATCHES:
        UNREACHED_PATCHES.append(patch_rel)


def _patch_change_already_present(repo_dir: str, patch: Path) -> bool:
    try:
        text = patch.read_text()
    except OSError:
        return False
    current_file = None
    added: dict[str, list[str]] = {}
    removed: dict[str, list[str]] = {}
    for line in text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
            added.setdefault(current_file, [])
            removed.setdefault(current_file, [])
        elif line.startswith("+") and not line.startswith("+++") and current_file:
            added[current_file].append(line[1:])
        elif line.startswith("-") and not line.startswith("--") and current_file:
            removed[current_file].append(line[1:])
    for filepath, added_lines in added.items():
        target = Path(repo_dir) / filepath
        if not target.exists():
            return False
        try:
            content = target.read_text()
        except OSError:
            return False
        if all(line in content for line in added_lines):
            continue
        removed_lines = removed.get(filepath, [])
        if removed_lines and all(line not in content for line in removed_lines):
            continue
        return False
    return True


def print_failures() -> int:
    if UNREACHED_PATCHES:
        reporting.blank()
        reporting.print_line("[bold red]Patches never applied (series stopped before reaching them):[/]")
        for p in UNREACHED_PATCHES:
            reporting.print_line(f"  ! {p}")
    if NOT_NEEDED_PATCHES:
        reporting.blank()
        reporting.print_line("[bold cyan]Patches not needed for this AOSP version:[/]")
        for p in NOT_NEEDED_PATCHES:
            reporting.print_line(f"  - {p}")
    if FAILED_PATCHES:
        reporting.blank()
        reporting.print_line("[bold yellow]Patches needing regeneration:[/]")
        for p in FAILED_PATCHES:
            reporting.print_line(f"  x {p}")
    return 0


def print_summary() -> None:
    if not SERIES_STATS:
        _print_skipped_listing()
        return
    reporting.blank()
    reporting.print_line("Patch Series Summary")
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
        reporting.print_line(f"  {sdir}: {a} applied, {s} skipped, {n} not needed, {f} failed")
    reporting.print_line(f"  Total: {t_a} applied, {t_s} skipped, {t_n} not needed, {t_f} failed")
    _print_skipped_listing()


def _print_skipped_listing() -> None:
    """Name every skipped (already-present) patch, not just count it.

    A count alone cannot be checked against anything: a patch that silently
    failed to apply also lands in "skipped" when its change looks present, so
    the listing is the only way to see what was actually left out.
    """
    if not SKIPPED_PATCHES:
        return
    reporting.blank()
    reporting.print_line("Skipped (diff already present, no new commit):")
    for p in SKIPPED_PATCHES:
        reporting.print_line(f"  = {p}")


def unreached_for_series(series_dir: str, all_patches: list[str]) -> list[str]:
    """Patches in a series that produced no outcome this run."""
    return [f"{series_dir}/{p}" for p in all_patches if f"{series_dir}/{p}" not in PATCH_OUTCOMES]


def trim_manifest_line(line: str) -> str:
    return line.split("#")[0].strip()


def run_patch_on_repo(series_dir: str, repo_dir: str, patch_name: str, mode: str) -> bool:
    patch = SCRIPT_DIR / series_dir / patch_name
    patch_rel = f"{series_dir}/{patch_name}"

    if not patch.exists():
        mark_failed(patch_rel)
        if mode != "probe":
            record_patch_result(series_dir, "failed", patch_rel)
        return False

    if is_patch_applied(repo_dir, patch, series_dir):
        if mode != "probe":
            logger.info("Skipping duplicate patch: %s", patch_rel)
            mark_skipped(patch_rel)
            record_patch_result(series_dir, "skipped", patch_rel)
        return True

    result = git("am", "-3", str(patch), cwd=Path(repo_dir), check=False, capture=False)
    if result.returncode == 0:
        if mode == "apply":
            logger.info("Applied patch: %s", patch_rel)
        elif mode == "dry-run":
            logger.info("Would apply patch: %s", patch_rel)
        if mode != "probe":
            record_patch_result(series_dir, "applied", patch_rel)
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
                not_needed = _patch_change_already_present(repo_dir, patch)
        if not_needed:
            mark_not_needed(patch_rel)
            record_patch_result(series_dir, "not_needed", patch_rel)
        else:
            mark_failed(patch_rel)
            record_patch_result(series_dir, "failed", patch_rel)
    return False


def run_patch_sequence(series_dir: str, repo_dir: str, mode: str, *patch_names: str) -> bool:
    for i, pn in enumerate(patch_names):
        if not run_patch_on_repo(series_dir, repo_dir, pn, mode):
            if mode != "probe":
                # Everything after the failure never ran. Say so out loud
                # instead of letting the series quietly look complete.
                for skipped_over in patch_names[i + 1 :]:
                    mark_unreached(f"{series_dir}/{skipped_over}")
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
