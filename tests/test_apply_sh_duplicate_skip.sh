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
)

FIRST_CONTENT="$(<"$TARGET_DIR/demo.txt")"
if [ "$FIRST_CONTENT" != 'hello world' ]; then
    printf 'first apply content mismatch: %s\n' "$FIRST_CONTENT" >&2
    exit 1
fi

SECOND_LOG="$TMP_DIR/second-run.log"
if ! (
    cd "$AOSP_ROOT"
    "$SERIES_ROOT/apply.sh" --mb
) >"$SECOND_LOG" 2>&1; then
    printf 'expected duplicate patch run to succeed, but it failed\n' >&2
    cat "$SECOND_LOG" >&2
    exit 1
fi

SECOND_CONTENT="$(<"$TARGET_DIR/demo.txt")"
if [ "$SECOND_CONTENT" != 'hello world' ]; then
    printf 'second apply content mismatch: %s\n' "$SECOND_CONTENT" >&2
    exit 1
fi

if ! grep -q 'Skipping duplicate patch:' "$SECOND_LOG"; then
    printf 'expected duplicate skip message in second run log\n' >&2
    cat "$SECOND_LOG" >&2
    exit 1
fi

if grep -q 'Patch already applied' "$SECOND_LOG"; then
    printf 'expected apply.sh to skip before invoking git am on duplicate patch\n' >&2
    cat "$SECOND_LOG" >&2
    exit 1
fi
