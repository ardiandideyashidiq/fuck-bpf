import argparse
import json
import logging
import sys
from pathlib import Path

from scripts import STATE_FILENAME
from scripts.core import apply_series, cleanup_series_fallback, dry_run_series, list_patch_dirs, verify_series
from scripts.manifest import print_failures
from scripts.state import cleanup_from_state

logger = logging.getLogger("fuck-bpf")


def setup_logging(verbose: bool, quiet: bool, log_json: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.WARNING if quiet else logging.INFO

    root = logging.getLogger("fuck-bpf")
    root.setLevel(level)
    root.handlers.clear()

    if log_json:
        handler = logging.StreamHandler(sys.stderr)

        class JsonFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                return json.dumps(
                    {
                        "time": self.formatTime(record),
                        "level": record.levelname,
                        "logger": record.name,
                        "message": record.getMessage(),
                    }
                )

        handler.setFormatter(JsonFormatter())
        root.addHandler(handler)
    else:
        logging.basicConfig(level=level, format="[%(levelname)s] %(message)s", stream=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="apply.py",
        description="Fuck-BPF patch series manager",
    )
    parser.add_argument("--mb", action="store_true", help="Apply all patch series")
    parser.add_argument("--dry-run", action="store_true", help="Check whether all series would apply cleanly")
    parser.add_argument("--verify", action="store_true", help="Check target repos for clean worktrees and am state")
    parser.add_argument("--cleanup", action="store_true", help="Abort am sessions and reset target repos destructively")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("-q", "--quiet", action="store_true", help="Quiet output (warnings only)")
    parser.add_argument("--log-format", choices=["text", "json"], default="text", help="Log output format")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    setup_logging(args.verbose, args.quiet, args.log_format == "json")

    mode_count = sum([args.mb, args.dry_run, args.verify, args.cleanup])
    if mode_count == 0:
        parser.print_help()
        return 2
    if mode_count > 1:
        logger.error("Only one mode can be specified")
        return 2

    series_dirs = list_patch_dirs()
    if not series_dirs:
        logger.warning("No patch directories found")
        return 0

    exit_code = 0
    state_file = Path.cwd() / STATE_FILENAME

    if args.cleanup and state_file.exists():
        return cleanup_from_state()

    for series_dir in series_dirs:
        target = Path.cwd() / series_dir
        if not target.is_dir():
            logger.warning("Target directory missing: %s", series_dir)
            if args.verify:
                exit_code = 1
            continue

        try:
            if args.mb:
                apply_series(series_dir)
            elif args.dry_run:
                if not dry_run_series(series_dir):
                    exit_code = 1
            elif args.verify:
                if verify_series(series_dir) != 0:
                    exit_code = 1
            elif args.cleanup:
                cleanup_series_fallback(series_dir)
        except Exception as e:
            logger.error("Error processing %s: %s", series_dir, e)
            exit_code = 1

    if print_failures() != 0:
        exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
