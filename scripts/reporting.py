import re
import sys

_MARKUP_RE = re.compile(r"\[/?[A-Za-z0-9_\- .]*\]")


def strip_markup(text: str) -> str:
    return _MARKUP_RE.sub("", text)


class PlainReporter:
    def __init__(self, stream=None):
        self._stream = stream if stream is not None else sys.stderr

    def print_line(self, *objects) -> None:
        print(*[strip_markup(str(o)) for o in objects], file=self._stream)

    def header(self, title: str) -> None:
        self.print_line(f"=== {title} ===")

    def blank(self) -> None:
        print(file=self._stream)


_reporter = PlainReporter()


def set_reporter(reporter) -> None:
    global _reporter
    _reporter = reporter


def print_line(*objects) -> None:
    _reporter.print_line(*objects)


def header(title: str) -> None:
    _reporter.header(title)


def blank() -> None:
    _reporter.blank()
