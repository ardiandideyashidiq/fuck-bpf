from pathlib import Path

from .conftest import run_apply


def test_verify_clean_repo(integration_env: tuple[Path, Path, Path]) -> None:
    aosp_root, series_root, target = integration_env
    patch_dir = series_root / "demo" / "project"

    # Create a dummy patch so list_patch_dirs finds the series
    (patch_dir / "0001-dummy.patch").write_text("dummy\n")

    proc = run_apply(series_root, aosp_root, "--verify")
    assert proc.returncode == 0
    assert "git am clean" in proc.stderr


def test_verify_dirty_repo(integration_env: tuple[Path, Path, Path]) -> None:
    aosp_root, series_root, target = integration_env
    patch_dir = series_root / "demo" / "project"

    (patch_dir / "0001-dummy.patch").write_text("dummy\n")
    (target / "dirty.txt").write_text("should make it dirty")

    proc = run_apply(series_root, aosp_root, "--verify")
    assert proc.returncode == 1
    assert "working tree not clean" in proc.stderr


def test_verify_missing_target(integration_env: tuple[Path, Path, Path]) -> None:
    aosp_root, series_root, _ = integration_env
    # Don't create target directory - should still work
    proc = run_apply(series_root, aosp_root, "--verify")
    assert proc.returncode == 0
