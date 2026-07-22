import io

import pytest
from rich.console import Console

from scripts.manifest import (
    FAILED_PATCHES,
    SERIES_STATS,
    mark_failed,
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


class TestReportingFunctions:
    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        reset_results()

    def _make_console(self) -> tuple[Console, io.StringIO]:
        buf = io.StringIO()
        return Console(file=buf, force_terminal=True, highlight=False), buf

    def test_record_patch_result_initializes_series(self) -> None:
        record_patch_result("system/bpf", "applied")
        assert SERIES_STATS["system/bpf"]["applied"] == 1
        assert SERIES_STATS["system/bpf"]["skipped"] == 0
        assert SERIES_STATS["system/bpf"]["failed"] == 0

    def test_record_patch_result_increments(self) -> None:
        record_patch_result("system/bpf", "applied")
        record_patch_result("system/bpf", "applied")
        record_patch_result("system/bpf", "skipped")
        assert SERIES_STATS["system/bpf"]["applied"] == 2
        assert SERIES_STATS["system/bpf"]["skipped"] == 1

    def test_record_patch_result_multiple_series(self) -> None:
        record_patch_result("system/bpf", "applied")
        record_patch_result("system/netd", "failed")
        assert SERIES_STATS["system/bpf"]["applied"] == 1
        assert SERIES_STATS["system/netd"]["failed"] == 1

    def test_mark_failed(self) -> None:
        mark_failed("system/bpf/0001-foo.patch")
        assert FAILED_PATCHES == ["system/bpf/0001-foo.patch"]

    def test_print_failures_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        con, buf = self._make_console()
        monkeypatch.setattr("scripts.manifest._console", con)
        result = print_failures()
        assert result == 0
        assert buf.getvalue() == ""

    def test_print_failures_with_failures(self, monkeypatch: pytest.MonkeyPatch) -> None:
        con, buf = self._make_console()
        monkeypatch.setattr("scripts.manifest._console", con)
        mark_failed("system/bpf/0001-foo.patch")
        print_failures()
        output = buf.getvalue()
        assert "Patches needing regeneration" in output
        assert "system/bpf/0001-foo.patch" in output

    def test_print_summary_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        con, buf = self._make_console()
        monkeypatch.setattr("scripts.manifest._console", con)
        print_summary()
        assert buf.getvalue() == ""

    def test_print_summary_with_data(self, monkeypatch: pytest.MonkeyPatch) -> None:
        con, buf = self._make_console()
        monkeypatch.setattr("scripts.manifest._console", con)
        record_patch_result("system/bpf", "applied")
        record_patch_result("system/bpf", "skipped")
        record_patch_result("system/netd", "failed")
        print_summary()
        output = buf.getvalue()
        assert "Patch Series Summary" in output
        assert "system/bpf" in output
        assert "system/netd" in output
        assert "Total" in output
        assert "1" in output

    def test_reset_results(self) -> None:
        record_patch_result("system/bpf", "applied")
        mark_failed("system/bpf/0001-foo.patch")
        assert SERIES_STATS
        assert FAILED_PATCHES
        reset_results()
        assert not SERIES_STATS
        assert not FAILED_PATCHES
