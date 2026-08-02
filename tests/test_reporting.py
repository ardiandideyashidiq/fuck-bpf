import io

from scripts import reporting


def test_strip_markup_removes_tags() -> None:
    assert reporting.strip_markup("[bold red]Usage:[/] x <y>") == "Usage: x <y>"


def test_strip_markup_plain_text() -> None:
    assert reporting.strip_markup("no markup here") == "no markup here"


def test_plain_reporter_print_line_strips_markup() -> None:
    buf = io.StringIO()
    reporter = reporting.PlainReporter(stream=buf)
    reporter.print_line("[bold cyan]not needed[/]")
    assert buf.getvalue() == "not needed\n"


def test_plain_reporter_header() -> None:
    buf = io.StringIO()
    reporter = reporting.PlainReporter(stream=buf)
    reporter.header("system/bpf")
    assert buf.getvalue() == "=== system/bpf ===\n"


def test_plain_reporter_blank() -> None:
    buf = io.StringIO()
    reporter = reporting.PlainReporter(stream=buf)
    reporter.blank()
    assert buf.getvalue() == "\n"


def test_set_reporter_switches_output() -> None:
    original = reporting._reporter
    try:
        buf = io.StringIO()
        reporting.set_reporter(reporting.PlainReporter(stream=buf))
        reporting.print_line("hello")
        assert buf.getvalue() == "hello\n"
    finally:
        reporting.set_reporter(original)
