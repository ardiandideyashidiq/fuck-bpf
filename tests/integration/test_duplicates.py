import subprocess
from pathlib import Path

from .conftest import run_apply


def test_duplicate_skip_via_patch_id(integration_env: tuple[Path, Path, Path]) -> None:
    aosp_root, series_root, target = integration_env
    patch_dir = series_root / "demo" / "project"

    (target / "demo.txt").write_text("change")
    subprocess.run(["git", "add", "demo.txt"], cwd=target, capture_output=True, check=True)
    subprocess.run(
        ["git", "-c", "user.name=T", "-c", "user.email=t@t", "commit", "-m", "first"],
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
    (patch_dir / "0001-first.patch").write_text(result.stdout)

    # Make second patch
    (target / "demo.txt").write_text("another change")
    subprocess.run(["git", "add", "demo.txt"], cwd=target, capture_output=True, check=True)
    subprocess.run(
        ["git", "-c", "user.name=T", "-c", "user.email=t@t", "commit", "-m", "second"],
        cwd=target,
        capture_output=True,
        check=True,
    )
    result2 = subprocess.run(
        ["git", "format-patch", "-1", "HEAD", "--stdout"],
        cwd=target,
        capture_output=True,
        text=True,
        check=True,
    )
    (patch_dir / "0002-second.patch").write_text(result2.stdout)

    # Reset both
    subprocess.run(["git", "reset", "--hard", "HEAD~2"], cwd=target, capture_output=True, check=True)

    # Apply both — these become the only commits
    run_apply(series_root, aosp_root, "--mb")

    # Apply again — both should be skipped since their diff is already in the tree
    proc = run_apply(series_root, aosp_root, "--mb")
    assert proc.returncode == 0
    assert "Skipping duplicate patch:" in proc.stderr
