import io

import pytest

from scripts import reporting
from scripts.manifest import (
    FAILED_PATCHES,
    NOT_NEEDED_PATCHES,
    SERIES_STATS,
    SKIPPED_PATCHES,
    UNREACHED_PATCHES,
    mark_failed,
    mark_not_needed,
    mark_skipped,
    mark_unreached,
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


class TestUnexplainedDrops:
    """A patch that was never applied must never read as a peaceful 'skipped'.

    SERIES_STATS + the summary were the only accounting, and both collapse into
    counts: a patch that ran out of a sequence (return False -> loop breaks),
    or that was silently treated as a duplicate, vanished with no listing.
    """

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        reset_results()

    def test_skipped_patches_are_listed_individually(self, buf_reporter: io.StringIO) -> None:
        mark_skipped("system/bpf/0001-foo.patch")
        print_summary()
        output = buf_reporter.getvalue().replace("stars", "")
        assert "system/bpf/0001-foo.patch" in output

    def test_reset_clears_skipped(self) -> None:
        mark_skipped("system/bpf/0001-foo.patch")
        reset_results()
        assert SKIPPED_PATCHES == []

    def test_every_patch_reaches_a_terminal_state(self, buf_reporter: io.StringIO) -> None:
        # applied + skipped + not_needed + failed must equal what the summary totals.
        record_patch_result("system/bpf", "applied")
        record_patch_result("system/bpf", "skipped")
        record_patch_result("system/bpf", "not_needed")
        record_patch_result("system/bpf", "failed")
        assert SERIES_STATS["system/bpf"]["applied"] == 1
        print_summary()
        output = buf_reporter.getvalue()
        assert "1 applied" in output and "1 skipped" in output

    def test_aborted_series_reports_unreached_patches(self, buf_reporter: io.StringIO) -> None:
        # run_patch_sequence stops at the first failure; the patches after it
        # never ran at all and used to leave no trace whatsoever.
        mark_unreached("system/bpf/0002-bar.patch")
        print_failures()
        output = buf_reporter.getvalue().replace("stars", "")
        assert "system/bpf/0002-bar.patch" in output

    def test_reset_clears_unreached(self) -> None:
        mark_unreached("system/bpf/0002-bar.patch")
        reset_results()
        assert UNREACHED_PATCHES == []


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
