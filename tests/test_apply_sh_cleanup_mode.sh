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

printf 'dirty\n' >> "$TARGET_DIR/demo.txt"

NOARG_LOG="$TMP_DIR/noarg.log"
STATUS=0
(
    cd "$AOSP_ROOT"
    "$SERIES_ROOT/apply.sh"
) >"$NOARG_LOG" 2>&1 || STATUS=$?

if [ "$STATUS" -eq 0 ]; then
    printf 'expected no-arg apply.sh invocation to fail\n' >&2
    cat "$NOARG_LOG" >&2
    exit 1
fi

if ! grep -q 'Usage:' "$NOARG_LOG"; then
    printf 'expected usage output for no-arg invocation\n' >&2
    cat "$NOARG_LOG" >&2
    exit 1
fi

CURRENT_CONTENT="$(<"$TARGET_DIR/demo.txt")"
if [ "$CURRENT_CONTENT" != $'hello\ndirty' ]; then
    printf 'expected no-arg invocation to leave worktree untouched\n' >&2
    exit 1
fi

BADARG_LOG="$TMP_DIR/badarg.log"
STATUS=0
(
    cd "$AOSP_ROOT"
    "$SERIES_ROOT/apply.sh" --wat
) >"$BADARG_LOG" 2>&1 || STATUS=$?

if [ "$STATUS" -eq 0 ]; then
    printf 'expected unknown mode to fail\n' >&2
    cat "$BADARG_LOG" >&2
    exit 1
fi

if ! grep -q 'Usage:' "$BADARG_LOG"; then
    printf 'expected usage output for unknown mode\n' >&2
    cat "$BADARG_LOG" >&2
    exit 1
fi

if [ "$(<"$TARGET_DIR/demo.txt")" != $'hello\ndirty' ]; then
    printf 'expected unknown mode to leave worktree untouched\n' >&2
    exit 1
fi

(
    cd "$AOSP_ROOT"
    "$SERIES_ROOT/apply.sh" --cleanup
) >/dev/null

if [ "$(<"$TARGET_DIR/demo.txt")" != 'hello' ]; then
    printf 'expected cleanup mode to restore clean base tree\n' >&2
    exit 1
fi
