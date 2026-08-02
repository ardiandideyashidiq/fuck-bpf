import io

import pytest

from scripts import reporting
from scripts.manifest import (
    FAILED_PATCHES,
    NOT_NEEDED_PATCHES,
    SERIES_STATS,
    mark_failed,
    mark_not_needed,
    print_failures,
    print_summary,
    record_patch_result,
    reset_results,
    trim_manifest_line,
)


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


@pytest.fixture
def buf_reporter(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    original = reporting._reporter
    buf = io.StringIO()
    reporting.set_reporter(reporting.PlainReporter(stream=buf))
    yield buf
    reporting.set_reporter(original)


class TestReportingFunctions:
    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        reset_results()

    def test_record_patch_result_initializes_series(self) -> None:
        record_patch_result("system/bpf", "applied")
        assert SERIES_STATS["system/bpf"]["applied"] == 1
        assert SERIES_STATS["system/bpf"]["skipped"] == 0
        assert SERIES_STATS["system/bpf"]["failed"] == 0
        assert SERIES_STATS["system/bpf"]["not_needed"] == 0

    def test_record_patch_result_increments(self) -> None:
        record_patch_result("system/bpf", "applied")
        record_patch_result("system/bpf", "applied")
        record_patch_result("system/bpf", "skipped")
        assert SERIES_STATS["system/bpf"]["applied"] == 2
        assert SERIES_STATS["system/bpf"]["skipped"] == 1

    def test_record_patch_result_multiple_series(self) -> None:
        record_patch_result("system/bpf", "applied")
        record_patch_result("system/netd", "not_needed")
        assert SERIES_STATS["system/bpf"]["applied"] == 1
        assert SERIES_STATS["system/netd"]["not_needed"] == 1

    def test_mark_failed(self) -> None:
        mark_failed("system/bpf/0001-foo.patch")
        assert FAILED_PATCHES == ["system/bpf/0001-foo.patch"]

    def test_mark_not_needed(self) -> None:
        mark_not_needed("system/bpf/0001-foo.patch")
        assert NOT_NEEDED_PATCHES == ["system/bpf/0001-foo.patch"]

    def test_print_failures_empty(self, buf_reporter: io.StringIO) -> None:
        result = print_failures()
        assert result == 0
        assert buf_reporter.getvalue() == ""

    def test_print_failures_only_not_needed(self, buf_reporter: io.StringIO) -> None:
        mark_not_needed("system/bpf/0001-foo.patch")
        print_failures()
        output = buf_reporter.getvalue()
        assert "not needed" in output
        assert "system/bpf/0001-foo.patch" in output
        assert "Patches needing regeneration" not in output

    def test_print_failures_with_failures(self, buf_reporter: io.StringIO) -> None:
        mark_failed("system/bpf/0001-foo.patch")
        print_failures()
        output = buf_reporter.getvalue()
        assert "Patches needing regeneration" in output
        assert "system/bpf/0001-foo.patch" in output

    def test_print_failures_both_categories(self, buf_reporter: io.StringIO) -> None:
        mark_not_needed("a/001.patch")
        mark_failed("b/001.patch")
        print_failures()
        output = buf_reporter.getvalue()
        assert "not needed" in output
        assert "a/001.patch" in output
        assert "Patches needing regeneration" in output
        assert "b/001.patch" in output

    def test_print_summary_empty(self, buf_reporter: io.StringIO) -> None:
        print_summary()
        assert buf_reporter.getvalue() == ""

    def test_print_summary_with_data(self, buf_reporter: io.StringIO) -> None:
        record_patch_result("system/bpf", "applied")
        record_patch_result("system/bpf", "skipped")
        record_patch_result("system/bpf", "not_needed")
        record_patch_result("system/netd", "failed")
        print_summary()
        output = buf_reporter.getvalue()
        assert "Patch Series Summary" in output
        assert "system/bpf" in output
        assert "system/netd" in output
        assert "Total" in output
        assert "not needed" in output
        assert "1" in output

    def test_reset_results(self) -> None:
        record_patch_result("system/bpf", "applied")
        mark_failed("system/bpf/0001-foo.patch")
        mark_not_needed("system/bpf/0002-bar.patch")
        assert SERIES_STATS
        assert FAILED_PATCHES
        assert NOT_NEEDED_PATCHES
        reset_results()
        assert not SERIES_STATS
        assert not FAILED_PATCHES
        assert not NOT_NEEDED_PATCHES
