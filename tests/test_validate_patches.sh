#!/bin/bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

SOURCE_ROOT="$TMP_DIR/source"
PATCH_REPO="$TMP_DIR/fuck-bpf"
TARGET_DIR="$SOURCE_ROOT/demo/project"
PATCH_DIR="$PATCH_REPO/demo/project"

mkdir -p "$TARGET_DIR" "$PATCH_DIR"
if [ -d "$REPO_ROOT/scripts" ]; then
    cp -R "$REPO_ROOT/scripts" "$PATCH_REPO/scripts"
fi

git init "$TARGET_DIR" >/dev/null
printf 'hello\n' > "$TARGET_DIR/demo.txt"
git -C "$TARGET_DIR" add demo.txt
git -C "$TARGET_DIR" -c user.name='Test User' -c user.email='test@example.com' commit -m 'base' >/dev/null

printf 'hello world\n' > "$TARGET_DIR/demo.txt"
git -C "$TARGET_DIR" add demo.txt
git -C "$TARGET_DIR" -c user.name='Test User' -c user.email='test@example.com' commit -m 'update demo' >/dev/null
git -C "$TARGET_DIR" format-patch -1 HEAD --stdout > "$PATCH_DIR/0001-update-demo.patch"
git -C "$TARGET_DIR" reset --hard HEAD~1 >/dev/null

VALIDATE_LOG="$TMP_DIR/validate.log"
bash "$PATCH_REPO/scripts/validate-patches.sh" "$SOURCE_ROOT" >"$VALIDATE_LOG" 2>&1

if ! grep -q 'Series applies cleanly: demo/project' "$VALIDATE_LOG"; then
    printf 'expected validation success output\n' >&2
    cat "$VALIDATE_LOG" >&2
    exit 1
fi

printf 'broken\n' > "$TARGET_DIR/demo.txt"
git -C "$TARGET_DIR" add demo.txt
git -C "$TARGET_DIR" -c user.name='Test User' -c user.email='test@example.com' commit -m 'break apply' >/dev/null

FAIL_LOG="$TMP_DIR/validate-fail.log"
STATUS=0
bash "$PATCH_REPO/scripts/validate-patches.sh" "$SOURCE_ROOT" >"$FAIL_LOG" 2>&1 || STATUS=$?

if [ "$STATUS" -eq 0 ]; then
    printf 'expected validation to fail on conflicting source tree\n' >&2
    cat "$FAIL_LOG" >&2
    exit 1
fi

if ! grep -q 'Series failed: demo/project' "$FAIL_LOG"; then
    printf 'expected validation failure output\n' >&2
    cat "$FAIL_LOG" >&2
    exit 1
fi
