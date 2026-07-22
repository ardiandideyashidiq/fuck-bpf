import subprocess
from pathlib import Path

from .conftest import run_apply


def test_dry_run_reports_would_apply(integration_env: tuple[Path, Path, Path]) -> None:
    aosp_root, series_root, target = integration_env
    patch_dir = series_root / "demo" / "project"

    (target / "demo.txt").write_text("hello world")
    subprocess.run(["git", "add", "demo.txt"], cwd=target, capture_output=True, check=True)
    subprocess.run(
        ["git", "-c", "user.name=T", "-c", "user.email=t@t", "commit", "-m", "update"],
        cwd=target,
        capture_output=True,
        check=True,
    )
    result = subprocess.run(
        ["git", "format-patch", "-1", "HEAD", "--stdout"],
        cwd=target,
        capture_output=True,
        text=True,
        check=True,
    )
    (patch_dir / "0001-update.patch").write_text(result.stdout)
    subprocess.run(["git", "reset", "--hard", "HEAD~1"], cwd=target, capture_output=True, check=True)

    proc = run_apply(series_root, aosp_root, "--dry-run")
    assert proc.returncode == 0
    assert "Would apply patch:" in proc.stderr
