import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def integration_env(tmp_path: Path) -> Iterator[tuple[Path, Path, Path]]:
    aosp = tmp_path / "aosp"
    series_root = tmp_path / "fuck-bpf"
    target = aosp / "demo" / "project"
    patch_dir = series_root / "demo" / "project"

    target.mkdir(parents=True)
    patch_dir.mkdir(parents=True)

    subprocess.run(["git", "init"], cwd=target, capture_output=True, check=True)
    subprocess.run(
        ["git", "-c", "user.name=T", "-c", "user.email=t@t", "commit", "--allow-empty", "-m", "base"],
        cwd=target,
        capture_output=True,
        check=True,
    )

    # Copy apply.py and scripts/ into the fake fuck-bpf tree
    shutil.copy2(REPO_ROOT / "apply.py", series_root / "apply.py")
    shutil.copytree(REPO_ROOT / "scripts", series_root / "scripts", dirs_exist_ok=True)

    yield (aosp, series_root, target)


def run_apply(series_root: Path, aosp_root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["python3", str(series_root / "apply.py"), *args],
        cwd=str(aosp_root),
        capture_output=True,
        text=True,
    )
