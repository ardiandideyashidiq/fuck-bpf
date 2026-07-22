from scripts.manifest import trim_manifest_line


class TestTrimManifestLine:
    def test_basic(self) -> None:
        assert trim_manifest_line("patch 0001-foo.patch") == "patch 0001-foo.patch"

    def test_comment(self) -> None:
        assert trim_manifest_line("patch 0001-foo.patch  # this is a comment") == "patch 0001-foo.patch"

    def test_only_comment(self) -> None:
        assert trim_manifest_line("  # comment only  ") == ""

    def test_whitespace(self) -> None:
        assert trim_manifest_line("  ") == ""

    def test_empty(self) -> None:
        assert trim_manifest_line("") == ""

    def test_leading_trailing_spaces(self) -> None:
        assert trim_manifest_line("  choice name  ") == "choice name"
