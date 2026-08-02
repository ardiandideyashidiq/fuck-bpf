import logging

from rich.console import Console
from rich.logging import RichHandler


class RichReporter:
    def __init__(self) -> None:
        self.console = Console(stderr=True, highlight=False)

    def print_line(self, *objects) -> None:
        self.console.print(*objects)

    def header(self, title: str) -> None:
        self.console.rule(title, align="left")

    def blank(self) -> None:
        self.console.print()


def make_logging_handler(level: int, show_locals: bool) -> logging.Handler:
    return RichHandler(
        level=level,
        console=Console(stderr=True),
        show_time=False,
        show_path=False,
        rich_tracebacks=True,
        tracebacks_show_locals=show_locals,
    )
