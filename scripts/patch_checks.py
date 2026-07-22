import re
import sys
from pathlib import Path


def check_mbox_footer(patch_files: list[Path]) -> int:
    exit_code = 0
    for f in patch_files:
        content = f.read_bytes()
        if not content.endswith(b"\n"):
            print(f"[BLOCKED] missing trailing newline: {f}")
            exit_code = 1
            continue
        lines = content.split(b"\n")
        if len(lines) < 3:
            print(f"[BLOCKED] too short for mbox footer: {f}")
            exit_code = 1
            continue
        if not (len(lines) >= 3 and lines[-3] == b"-- " and lines[-2] != b"" and lines[-1] == b""):
            print(f"[BLOCKED] missing mbox footer '-- ': {f}")
            exit_code = 1
    return exit_code


def check_no_patch_in_diff(patch_files: list[Path]) -> int:
    exit_code = 0
    pat = re.compile(r"^diff --git a/.*\.patch(?: |$)")
    for f in patch_files:
        for line in f.read_text().splitlines():
            if pat.match(line):
                print(f"[BLOCKED] patch creates or modifies another .patch file: {f}")
                exit_code = 1
                break
    return exit_code


def check_numbering_order(patch_files: list[Path]) -> int:
    exit_code = 0
    dirs: dict[str, list[Path]] = {}
    for f in patch_files:
        dirs.setdefault(str(f.parent), []).append(f)
    for d, patches in sorted(dirs.items()):
        prev = 0
        for patch in sorted(patches):
            m = re.match(r"^(\d+)", patch.name)
            if not m:
                print(f"[BLOCKED] patch file missing numeric prefix: {patch}")
                exit_code = 1
                continue
            num = int(m.group(1))
            if prev != 0 and num <= prev:
                print(f"[BLOCKED] patch numbering must increase in {d}: {patch.name}")
                exit_code = 1
            prev = num
    return exit_code


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <check-name> [files...]", file=sys.stderr)
        return 2

    check_name = sys.argv[1]
    patch_files = [Path(a) for a in sys.argv[2:] if a.endswith(".patch")]

    if not patch_files:
        return 0

    checks = {
        "mbox-footer": check_mbox_footer,
        "no-patch-in-diff": check_no_patch_in_diff,
        "numbering-order": check_numbering_order,
    }

    check_fn = checks.get(check_name)
    if not check_fn:
        print(f"Unknown check: {check_name}", file=sys.stderr)
        return 2

    return check_fn(patch_files)


if __name__ == "__main__":
    sys.exit(main())
