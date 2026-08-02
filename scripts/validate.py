import os
import shutil
import sys
import tempfile

from scripts import MANIFEST_NAME, SCRIPT_DIR, reporting
from scripts.git_helpers import git
from scripts.manifest import run_manifest_series


def main() -> int:
    source_root = os.environ.get("FUCK_BPF_SOURCE_ROOT", "")
    if not source_root and len(sys.argv) > 1:
        source_root = sys.argv[1]

    if not source_root:
        reporting.print_line("[bold red]Usage:[/] scripts/validate-patches.py <synced-source-root>")
        return 1

    source_root = os.path.abspath(source_root)
    if not os.path.isdir(source_root):
        reporting.print_line(f"[bold red]Synced source root not found:[/] {source_root}")
        return 1

    exit_code = 0
    for patch_dir in sorted(set(p.parent for p in SCRIPT_DIR.rglob("*.patch"))):
        series_dir = patch_dir.relative_to(SCRIPT_DIR).as_posix()
        series_path = os.path.join(source_root, series_dir)

        if not os.path.isdir(series_path):
            reporting.print_line(f"[bold red]Series missing source repo:[/] {series_dir}")
            exit_code = 1
            continue

        tmpdir = tempfile.mkdtemp(prefix="fuck-bpf-validate-")
        try:
            git("worktree", "add", tmpdir, "HEAD", cwd=series_path)
            series_ok = True

            manifest = SCRIPT_DIR / series_dir / MANIFEST_NAME
            if manifest.exists():
                series_ok = run_manifest_series(series_dir, tmpdir, "dry-run")
            else:
                for patch in sorted(patch_dir.glob("*.patch")):
                    result = git("apply", "--reverse", "--check", str(patch), cwd=tmpdir, check=False)
                    if result.returncode == 0:
                        continue

                    result = git("am", "-3", str(patch), cwd=tmpdir, check=False)
                    if result.returncode != 0:
                        reporting.print_line(f"[bold red]\u2717[/] Series failed: {series_dir}")
                        git("am", "--abort", cwd=tmpdir, check=False)
                        exit_code = 1
                        series_ok = False
                        break

            if series_ok:
                reporting.print_line(f"[bold green]\u2713[/] Series applies cleanly: {series_dir}")

        finally:
            git("worktree", "remove", "--force", tmpdir, cwd=series_path, check=False)
            shutil.rmtree(tmpdir, ignore_errors=True)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
