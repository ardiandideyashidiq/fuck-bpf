#!/bin/bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

AOSP_ROOT="$TMP_DIR/aosp"
SERIES_ROOT="$TMP_DIR/fuck-bpf"

mkdir -p "$AOSP_ROOT/demo/failing" "$AOSP_ROOT/demo/other" \
    "$SERIES_ROOT/demo/failing" "$SERIES_ROOT/demo/other"
cp "$REPO_ROOT/apply.sh" "$SERIES_ROOT/apply.sh"

for target in "$AOSP_ROOT/demo/failing" "$AOSP_ROOT/demo/other"; do
    git init "$target" >/dev/null
    printf 'base\n' > "$target/demo.txt"
    git -C "$target" add demo.txt
    git -C "$target" -c user.name='Test User' -c user.email='test@example.com' commit -m 'base' >/dev/null
done

cat > "$SERIES_ROOT/demo/failing/0001-stale.patch" <<'PATCH'
From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001
From: Test User <test@example.com>
Date: Tue, 1 Jan 2030 00:00:00 +0000
Subject: [PATCH] stale

diff --git a/demo.txt b/demo.txt
index df967b9..94954ab 100644
--- a/demo.txt
+++ b/demo.txt
@@ -1 +1 @@
-missing
+changed
PATCH

printf 'base\nother\n' > "$AOSP_ROOT/demo/other/demo.txt"
git -C "$AOSP_ROOT/demo/other" add demo.txt
git -C "$AOSP_ROOT/demo/other" -c user.name='Test User' -c user.email='test@example.com' commit -m 'other change' >/dev/null
git -C "$AOSP_ROOT/demo/other" format-patch -1 HEAD --stdout > "$SERIES_ROOT/demo/other/0001-other.patch"
git -C "$AOSP_ROOT/demo/other" reset --hard HEAD~1 >/dev/null

LOG="$TMP_DIR/apply.log"
STATUS=0
(
    cd "$AOSP_ROOT"
    "$SERIES_ROOT/apply.sh" --mb
) >"$LOG" 2>&1 || STATUS=$?

if [ "$STATUS" -eq 0 ]; then
    printf 'expected aggregate apply to fail after collecting regeneration list\n' >&2
    cat "$LOG" >&2
    exit 1
fi

if ! grep -q 'Applied patch: demo/other/0001-other.patch' "$LOG"; then
    printf 'expected independent series to continue after failed series\n' >&2
    cat "$LOG" >&2
    exit 1
fi

if ! grep -q 'Patches needing regeneration:' "$LOG"; then
    printf 'expected final regeneration summary header\n' >&2
    cat "$LOG" >&2
    exit 1
fi

if ! grep -q 'demo/failing/0001-stale.patch' "$LOG"; then
    printf 'expected failed patch in final regeneration summary\n' >&2
    cat "$LOG" >&2
    exit 1
fi

OTHER_CONTENT="$(<"$AOSP_ROOT/demo/other/demo.txt")"
if [ "$OTHER_CONTENT" != $'base\nother' ]; then
    printf 'expected other series to apply, got: %s\n' "$OTHER_CONTENT" >&2
    exit 1
fi
