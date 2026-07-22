from scripts.cli import build_parser


class TestBuildParser:
    def setup_method(self) -> None:
        self.parser = build_parser()

    def test_default_exits_2(self) -> None:
        args = self.parser.parse_args([])
        assert not args.mb
        assert not args.dry_run
        assert not args.verify
        assert not args.cleanup
        assert args.log_format == "text"

    def test_mb_flag(self) -> None:
        args = self.parser.parse_args(["--mb"])
        assert args.mb

    def test_dry_run_flag(self) -> None:
        args = self.parser.parse_args(["--dry-run"])
        assert args.dry_run

    def test_verify_flag(self) -> None:
        args = self.parser.parse_args(["--verify"])
        assert args.verify

    def test_cleanup_flag(self) -> None:
        args = self.parser.parse_args(["--cleanup"])
        assert args.cleanup

    def test_verbose(self) -> None:
        args = self.parser.parse_args(["--mb", "-v"])
        assert args.verbose

    def test_quiet(self) -> None:
        args = self.parser.parse_args(["--mb", "-q"])
        assert args.quiet

    def test_log_format_json(self) -> None:
        args = self.parser.parse_args(["--mb", "--log-format", "json"])
        assert args.log_format == "json"
