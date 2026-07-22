import subprocess
from pathlib import Path

from .conftest import run_apply


def test_cleanup_aborts_and_resets(integration_env: tuple[Path, Path, Path]) -> None:
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

    # Apply first
    run_apply(series_root, aosp_root, "--mb")

    # Add an untracked file
    (target / "untracked.txt").write_text("should be removed")

    # Cleanup
    proc = run_apply(series_root, aosp_root, "--cleanup")
    assert proc.returncode == 0

    # After cleanup, the untracked file should be gone
    assert not (target / "untracked.txt").exists()


def test_unknown_mode_exits_nonzero(integration_env: tuple[Path, Path, Path]) -> None:
    aosp_root, series_root, _ = integration_env
    proc = run_apply(series_root, aosp_root, "--wat")
    assert proc.returncode == 2
