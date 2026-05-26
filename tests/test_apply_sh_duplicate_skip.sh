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

STRICT_AOSP_ROOT="$TMP_DIR/strict-aosp"
STRICT_SERIES_ROOT="$TMP_DIR/strict-fuck-bpf"
STRICT_TARGET_DIR="$STRICT_AOSP_ROOT/demo/project"
STRICT_PATCH_DIR="$STRICT_SERIES_ROOT/demo/project"

mkdir -p "$STRICT_TARGET_DIR" "$STRICT_PATCH_DIR"
cp "$REPO_ROOT/apply.sh" "$STRICT_SERIES_ROOT/apply.sh"

git init "$STRICT_TARGET_DIR" >/dev/null
printf 'hello\n' > "$STRICT_TARGET_DIR/demo.txt"
git -C "$STRICT_TARGET_DIR" add demo.txt
git -C "$STRICT_TARGET_DIR" -c user.name='Test User' -c user.email='test@example.com' commit -m 'base' >/dev/null

printf 'different upstream change\n' > "$STRICT_TARGET_DIR/demo.txt"
git -C "$STRICT_TARGET_DIR" add demo.txt
git -C "$STRICT_TARGET_DIR" -c user.name='Test User' -c user.email='test@example.com' commit -m 'update demo' >/dev/null

cat > "$STRICT_PATCH_DIR/0001-corrupt-same-subject.patch" <<'PATCH'
From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001
From: Test User <test@example.com>
Date: Tue, 1 Jan 2030 00:00:00 +0000
Subject: [PATCH] update demo

This patch has a matching subject but no usable diff.
PATCH

STRICT_LOG="$TMP_DIR/strict-run.log"
STRICT_STATUS=0
(
    cd "$STRICT_AOSP_ROOT"
    "$STRICT_SERIES_ROOT/apply.sh" --mb
) >"$STRICT_LOG" 2>&1 || STRICT_STATUS=$?

if [ "$STRICT_STATUS" -eq 0 ]; then
    printf 'expected corrupt same-subject patch to fail instead of being skipped\n' >&2
    cat "$STRICT_LOG" >&2
    exit 1
fi

if ! grep -q 'Patch needs regeneration: demo/project/0001-corrupt-same-subject.patch' "$STRICT_LOG"; then
    printf 'expected regeneration error for corrupt same-subject patch\n' >&2
    cat "$STRICT_LOG" >&2
    exit 1
fi
