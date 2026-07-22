import os
from pathlib import Path

from scripts.state import has_series, state_path


def test_state_path() -> None:
    p = state_path()
    assert p.name == ".fuck-bpf-apply-state"


def test_has_series_no_file(tmp_path: Path) -> None:
    orig = Path.cwd()
    try:
        os.chdir(tmp_path)
        assert not has_series("foo/bar")
    finally:
        os.chdir(orig)
