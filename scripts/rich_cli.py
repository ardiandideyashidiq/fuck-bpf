import sys

from scripts.cli import main


def run() -> None:
    sys.exit(main(rich=True))


if __name__ == "__main__":
    run()
