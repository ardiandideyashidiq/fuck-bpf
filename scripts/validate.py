import os
import shutil
import subprocess
import sys
import tempfile

from scripts import SCRIPT_DIR


def git(*args: str, cwd: str, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        err = result.stderr.strip() or "unknown error"
        raise RuntimeError(f"git {' '.join(args)} failed: {err}")
    return result


def main() -> int:
    source_root = os.environ.get("FUCK_BPF_SOURCE_ROOT", "")
    if not source_root and len(sys.argv) > 1:
        source_root = sys.argv[1]

    if not source_root:
        print("Usage: scripts/validate-patches.py <synced-source-root>", file=sys.stderr)
        return 1

    source_root = os.path.abspath(source_root)
    if not os.path.isdir(source_root):
        print(f"Synced source root not found: {source_root}", file=sys.stderr)
        return 1

    exit_code = 0
    for patch_dir in sorted(set(p.parent for p in SCRIPT_DIR.rglob("*.patch"))):
        series_dir = patch_dir.relative_to(SCRIPT_DIR).as_posix()
        series_path = os.path.join(source_root, series_dir)

        if not os.path.isdir(series_path):
            print(f"Series missing source repo: {series_dir}", file=sys.stderr)
            exit_code = 1
            continue

        tmpdir = tempfile.mkdtemp(prefix="fuck-bpf-validate-")
        try:
            git("worktree", "add", tmpdir, "HEAD", cwd=series_path)
            series_ok = True

            for patch in sorted(patch_dir.glob("*.patch")):
                result = git("apply", "--reverse", "--check", str(patch), cwd=tmpdir, check=False)
                if result.returncode == 0:
                    continue

                result = git("am", "-3", str(patch), cwd=tmpdir, check=False)
                if result.returncode != 0:
                    print(f"Series failed: {series_dir}", file=sys.stderr)
                    git("am", "--abort", cwd=tmpdir, check=False)
                    exit_code = 1
                    series_ok = False
                    break

            if series_ok:
                print(f"Series applies cleanly: {series_dir}")

        finally:
            git("worktree", "remove", "--force", tmpdir, cwd=series_path, check=False)
            shutil.rmtree(tmpdir, ignore_errors=True)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
