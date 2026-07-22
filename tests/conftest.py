import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest


def init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, capture_output=True, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@test", "commit", "--allow-empty", "-m", "root"],
        cwd=path,
        capture_output=True,
        check=True,
    )


def make_commit(path: Path, filename: str, content: str, msg: str = "update") -> None:
    f = path / filename
    f.write_text(content)
    subprocess.run(["git", "add", filename], cwd=path, capture_output=True, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@test", "commit", "-m", msg],
        cwd=path,
        capture_output=True,
        check=True,
    )


def create_patch(path: Path, patch_name: str) -> Path:
    result = subprocess.run(
        ["git", "format-patch", "-1", "HEAD", "--stdout"],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )
    patch_file = path.parent / patch_name
    patch_file.write_text(result.stdout)
    return patch_file


@pytest.fixture
def tmp_repo() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d) / "repo"
        repo.mkdir(parents=True)
        init_git_repo(repo)
        yield repo


@pytest.fixture
def patch_series(tmp_repo: Path, tmp_path: Path) -> Iterator[tuple[Path, Path, Path]]:
    series_root = tmp_path / "series"
    series_dir = series_root / "demo" / "project"
    series_dir.mkdir(parents=True)
    yield (tmp_repo, series_root, series_dir)
