from pathlib import Path

from scripts.git_helpers import is_patch_applied, patch_id_for_file


def test_patch_id_for_file_nonexistent(tmp_path: Path) -> None:
    f = tmp_path / "nope.patch"
    f.write_text("not a patch")
    pid = patch_id_for_file(f)
    assert pid is None


def test_is_patch_applied_no_repo(tmp_path: Path) -> None:
    patch = tmp_path / "test.patch"
    patch.write_text("dummy")
    result = is_patch_applied(str(tmp_path), patch, "demo/project")
    assert result is False
