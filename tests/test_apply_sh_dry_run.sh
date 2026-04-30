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

printf 'hello world again\n' > "$TARGET_DIR/demo.txt"
git -C "$TARGET_DIR" add demo.txt
git -C "$TARGET_DIR" -c user.name='Test User' -c user.email='test@example.com' commit -m 'update demo again' >/dev/null
git -C "$TARGET_DIR" format-patch -1 HEAD --stdout > "$PATCH_DIR/0002-update-demo-again.patch"
git -C "$TARGET_DIR" reset --hard HEAD~2 >/dev/null

DRY_RUN_LOG="$TMP_DIR/dry-run.log"
(
    cd "$AOSP_ROOT"
    "$SERIES_ROOT/apply.sh" --dry-run
) >"$DRY_RUN_LOG" 2>&1

if ! grep -q 'Would apply patch: demo/project/0001-update-demo.patch' "$DRY_RUN_LOG"; then
    printf 'expected would-apply message in dry-run log\n' >&2
    cat "$DRY_RUN_LOG" >&2
    exit 1
fi

if ! grep -q 'Would apply patch: demo/project/0002-update-demo-again.patch' "$DRY_RUN_LOG"; then
    printf 'expected second dependent patch to dry-run cleanly\n' >&2
    cat "$DRY_RUN_LOG" >&2
    exit 1
fi

CURRENT_CONTENT="$(<"$TARGET_DIR/demo.txt")"
if [ "$CURRENT_CONTENT" != 'hello' ]; then
    printf 'dry-run modified content unexpectedly: %s\n' "$CURRENT_CONTENT" >&2
    exit 1
fi

(
    cd "$AOSP_ROOT"
    "$SERIES_ROOT/apply.sh" --mb
) >/dev/null

DUPLICATE_LOG="$TMP_DIR/duplicate-dry-run.log"
(
    cd "$AOSP_ROOT"
    "$SERIES_ROOT/apply.sh" --dry-run
) >"$DUPLICATE_LOG" 2>&1

if ! grep -q 'Skipping duplicate patch: demo/project/0001-update-demo.patch' "$DUPLICATE_LOG"; then
    printf 'expected duplicate skip message in dry-run duplicate log\n' >&2
    cat "$DUPLICATE_LOG" >&2
    exit 1
fi

if ! grep -q 'Skipping duplicate patch: demo/project/0002-update-demo-again.patch' "$DUPLICATE_LOG"; then
    printf 'expected duplicate skip message for second patch in dry-run duplicate log\n' >&2
    cat "$DUPLICATE_LOG" >&2
    exit 1
fi

printf 'HELLO\n' > "$TARGET_DIR/demo.txt"
git -C "$TARGET_DIR" add demo.txt
git -C "$TARGET_DIR" -c user.name='Test User' -c user.email='test@example.com' commit -m 'conflicting change' >/dev/null

CONFLICT_LOG="$TMP_DIR/conflict-dry-run.log"
STATUS=0
(
    cd "$AOSP_ROOT"
    "$SERIES_ROOT/apply.sh" --dry-run
) >"$CONFLICT_LOG" 2>&1 || STATUS=$?

if [ "$STATUS" -eq 0 ]; then
    printf 'expected dry-run to fail for conflicting patch\n' >&2
    cat "$CONFLICT_LOG" >&2
    exit 1
fi

if ! grep -q 'Would fail patch: demo/project/0001-update-demo.patch' "$CONFLICT_LOG"; then
    printf 'expected would-fail message in dry-run conflict log\n' >&2
    cat "$CONFLICT_LOG" >&2
    exit 1
fi

if grep -q 'Would fail patch: demo/project/0002-update-demo-again.patch' "$CONFLICT_LOG"; then
    printf 'did not expect the dependent patch to be checked after the first failure\n' >&2
    cat "$CONFLICT_LOG" >&2
    exit 1
fi
