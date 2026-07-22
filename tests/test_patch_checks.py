import tempfile
from pathlib import Path

from scripts.patch_checks import check_mbox_footer, check_no_patch_in_diff, check_numbering_order


class TestCheckMboxFooter:
    def test_valid(self) -> None:
        f = Path(tempfile.mktemp(suffix=".patch"))
        try:
            content = b"diff --git a/foo b/foo\nindex abc..def 100644\n"
            content += b"--- a/foo\n+++ b/foo\n@@ -1 +1 @@\n-hello\n+world\n-- \n2.43.0\n"
            f.write_bytes(content)
            assert check_mbox_footer([f]) == 0
        finally:
            f.unlink(missing_ok=True)

    def test_missing_trailing_newline(self) -> None:
        f = Path(tempfile.mktemp(suffix=".patch"))
        try:
            f.write_bytes(b"content\n-- \n2.43.0")
            assert check_mbox_footer([f]) == 1
        finally:
            f.unlink(missing_ok=True)

    def test_missing_mbox_footer(self) -> None:
        f = Path(tempfile.mktemp(suffix=".patch"))
        try:
            f.write_bytes(b"content\n")
            assert check_mbox_footer([f]) == 1
        finally:
            f.unlink(missing_ok=True)


class TestCheckNoPatchInDiff:
    def test_clean(self) -> None:
        f = Path(tempfile.mktemp(suffix=".patch"))
        try:
            f.write_text("diff --git a/foo.c b/foo.c\n")
            assert check_no_patch_in_diff([f]) == 0
        finally:
            f.unlink(missing_ok=True)

    def test_creates_patch(self) -> None:
        f = Path(tempfile.mktemp(suffix=".patch"))
        try:
            f.write_text("diff --git a/foo.patch b/foo.patch\n")
            assert check_no_patch_in_diff([f]) == 1
        finally:
            f.unlink(missing_ok=True)


class TestCheckNumberingOrder:
    def test_valid_sequence(self) -> None:
        d = Path(tempfile.mkdtemp())
        try:
            (d / "0001-first.patch").write_text("")
            (d / "0002-second.patch").write_text("")
            assert check_numbering_order(list(d.iterdir())) == 0
        finally:
            import shutil

            shutil.rmtree(d, ignore_errors=True)

    def test_missing_prefix(self) -> None:
        d = Path(tempfile.mkdtemp())
        try:
            (d / "bad.patch").write_text("")
            assert check_numbering_order(list(d.iterdir())) == 1
        finally:
            import shutil

            shutil.rmtree(d, ignore_errors=True)

    def test_non_increasing(self) -> None:
        d = Path(tempfile.mkdtemp())
        try:
            (d / "9-foo.patch").write_text("")
            (d / "10-bar.patch").write_text("")
            # Sorted alphabetically: 10-bar.patch < 9-foo.patch
            # But numeric: 9 then 10 — should be fine
            # We need a case where numeric decreases
            f1 = d / "0001-first.patch"
            f2 = d / "0001-dup.patch"
            f1.write_text("")
            f2.write_text("")
            # same number = not increasing
            assert check_numbering_order([f1, f2]) == 1
        finally:
            import shutil

            shutil.rmtree(d, ignore_errors=True)
