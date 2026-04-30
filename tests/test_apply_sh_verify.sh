#!/bin/bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

AOSP_ROOT="$TMP_DIR/aosp"
SERIES_ROOT="$TMP_DIR/fuck-bpf"
TARGET_DIR="$AOSP_ROOT/demo/project"
PATCH_DIR="$SERIES_ROOT/demo/project"

mkdir -p "$TARGET_DIR" "$PATCH_DIR"
cp "$REPO_ROOT/apply.sh" "$SERIES_ROOT/apply.sh"

git init "$TARGET_DIR" >/dev/null
printf 'hello\n' > "$TARGET_DIR/demo.txt"
git -C "$TARGET_DIR" add demo.txt
git -C "$TARGET_DIR" -c user.name='Test User' -c user.email='test@example.com' commit -m 'base' >/dev/null

printf 'hello world\n' > "$TARGET_DIR/demo.txt"
git -C "$TARGET_DIR" add demo.txt
git -C "$TARGET_DIR" -c user.name='Test User' -c user.email='test@example.com' commit -m 'update demo' >/dev/null
git -C "$TARGET_DIR" format-patch -1 HEAD --stdout > "$PATCH_DIR/0001-update-demo.patch"
git -C "$TARGET_DIR" reset --hard HEAD~1 >/dev/null

(
    cd "$AOSP_ROOT"
    "$SERIES_ROOT/apply.sh" --mb
) >/dev/null

VERIFY_LOG="$TMP_DIR/verify.log"
(
    cd "$AOSP_ROOT"
    "$SERIES_ROOT/apply.sh" --verify
) >"$VERIFY_LOG" 2>&1

if ! grep -q '== demo/project ==' "$VERIFY_LOG"; then
    printf 'expected verify output to include the series header\n' >&2
    cat "$VERIFY_LOG" >&2
    exit 1
fi

if ! grep -q 'git am clean' "$VERIFY_LOG"; then
    printf 'expected verify output to report clean git am state\n' >&2
    cat "$VERIFY_LOG" >&2
    exit 1
fi

printf 'dirty\n' >> "$TARGET_DIR/demo.txt"

DIRTY_LOG="$TMP_DIR/verify-dirty.log"
STATUS=0
(
    cd "$AOSP_ROOT"
    "$SERIES_ROOT/apply.sh" --verify
) >"$DIRTY_LOG" 2>&1 || STATUS=$?

if [ "$STATUS" -eq 0 ]; then
    printf 'expected verify mode to fail on dirty worktree\n' >&2
    cat "$DIRTY_LOG" >&2
    exit 1
fi

if ! grep -q 'working tree not clean' "$DIRTY_LOG"; then
    printf 'expected verify mode to report dirty worktree\n' >&2
    cat "$DIRTY_LOG" >&2
    exit 1
fi
