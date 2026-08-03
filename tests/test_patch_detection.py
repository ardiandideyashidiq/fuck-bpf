from pathlib import Path

from scripts.manifest import _patch_change_already_present


def _write_patch(path: Path, body: str) -> Path:
    header = "Subject: [PATCH] test\n\n---\n"
    footer = "\n-- \n2.34.1\n"
    path.write_text(header + body + footer)
    return path


def test_all_added_lines_present(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "foo.cpp").write_text("old line\nnew line\n")
    patch = _write_patch(
        tmp_path / "0001.patch",
        "diff --git a/foo.cpp b/foo.cpp\n--- a/foo.cpp\n+++ b/foo.cpp\n@@ -1 +1 @@\n-old line\n+new line\n",
    )
    assert _patch_change_already_present(str(repo), patch) is True


def test_removed_lines_all_absent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "foo.cpp").write_text("superseded line\n")
    patch = _write_patch(
        tmp_path / "0001.patch",
        "diff --git a/foo.cpp b/foo.cpp\n--- a/foo.cpp\n+++ b/foo.cpp\n@@ -1 +1 @@\n-old line\n+new line\n",
    )
    assert _patch_change_already_present(str(repo), patch) is True


def test_removed_lines_still_present(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "foo.cpp").write_text("old line\n")
    patch = _write_patch(
        tmp_path / "0001.patch",
        "diff --git a/foo.cpp b/foo.cpp\n--- a/foo.cpp\n+++ b/foo.cpp\n@@ -1 +1 @@\n-old line\n+new line\n",
    )
    assert _patch_change_already_present(str(repo), patch) is False


def test_missing_target_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    patch = _write_patch(
        tmp_path / "0001.patch",
        "diff --git a/nope.cpp b/nope.cpp\n--- a/nope.cpp\n+++ b/nope.cpp\n@@ -0,0 +1 @@\n+new line\n",
    )
    assert _patch_change_already_present(str(repo), patch) is False


def test_pure_add_patch_line_missing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "foo.cpp").write_text("other content\n")
    patch = _write_patch(
        tmp_path / "0001.patch",
        "diff --git a/foo.cpp b/foo.cpp\n"
        "--- a/foo.cpp\n"
        "+++ b/foo.cpp\n"
        "@@ -1,0 +1,2 @@\n"
        "+brand new line\n"
        "+another line\n",
    )
    assert _patch_change_already_present(str(repo), patch) is False


def test_removed_lines_absent_but_added_also_missing_with_context(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "foo.cpp").write_text("completely different\n")
    patch = _write_patch(
        tmp_path / "0001.patch",
        "diff --git a/foo.cpp b/foo.cpp\n--- a/foo.cpp\n+++ b/foo.cpp\n@@ -1 +1 @@\n-old line\n+new line\n",
    )
    assert _patch_change_already_present(str(repo), patch) is True


def test_missing_patch_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    patch = tmp_path / "nope.patch"
    assert _patch_change_already_present(str(repo), patch) is False


def test_empty_patch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    patch = tmp_path / "empty.patch"
    patch.write_text("")
    assert _patch_change_already_present(str(repo), patch) is True
