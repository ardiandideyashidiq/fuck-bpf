#!/bin/bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

SERIES_ROOT="$TMP_DIR/fuck-bpf"
mkdir -p "$SERIES_ROOT/demo/project"
cp "$REPO_ROOT/apply.sh" "$SERIES_ROOT/apply.sh"

write_manifest() {
    cat > "$SERIES_ROOT/demo/project/.fuck-bpf-series" <<'MANIFEST'
choice source-shape
option existing 0001-existing.patch
option restore 0002-restore.patch 0003-after-restore.patch
endchoice
MANIFEST
}

make_existing_fixture() {
    local root="$TMP_DIR/existing-aosp"
    local target="$root/demo/project"
    mkdir -p "$target"
    git init "$target" >/dev/null
    printf 'base\n' > "$target/demo.txt"
    git -C "$target" add demo.txt
    git -C "$target" -c user.name='Test User' -c user.email='test@example.com' commit -m 'base' >/dev/null

    printf 'base\nexisting\n' > "$target/demo.txt"
    git -C "$target" add demo.txt
    git -C "$target" -c user.name='Test User' -c user.email='test@example.com' commit -m 'existing change' >/dev/null
    git -C "$target" format-patch -1 HEAD --stdout > "$SERIES_ROOT/demo/project/0001-existing.patch"
    git -C "$target" reset --hard HEAD~1 >/dev/null
    printf '%s\n' "$root"
}

make_restore_fixture() {
    local root="$TMP_DIR/restore-aosp"
    local target="$root/demo/project"
    mkdir -p "$target"
    git init "$target" >/dev/null
    git -C "$target" -c user.name='Test User' -c user.email='test@example.com' commit --allow-empty -m 'base' >/dev/null

    printf 'base\n' > "$target/demo.txt"
    git -C "$target" add demo.txt
    git -C "$target" -c user.name='Test User' -c user.email='test@example.com' commit -m 'restore file' >/dev/null
    git -C "$target" format-patch -1 HEAD --stdout > "$SERIES_ROOT/demo/project/0002-restore.patch"

    printf 'base\nrestored\n' > "$target/demo.txt"
    git -C "$target" add demo.txt
    git -C "$target" -c user.name='Test User' -c user.email='test@example.com' commit -m 'after restore' >/dev/null
    git -C "$target" format-patch -1 HEAD --stdout > "$SERIES_ROOT/demo/project/0003-after-restore.patch"
    git -C "$target" reset --hard HEAD~2 >/dev/null
    printf '%s\n' "$root"
}

write_manifest
EXISTING_ROOT="$(make_existing_fixture)"
RESTORE_ROOT="$(make_restore_fixture)"

EXISTING_LOG="$TMP_DIR/existing.log"
(
    cd "$EXISTING_ROOT"
    "$SERIES_ROOT/apply.sh" --mb
) >"$EXISTING_LOG" 2>&1

if ! grep -q 'Selected patch option: demo/project source-shape existing' "$EXISTING_LOG"; then
    printf 'expected existing option selection\n' >&2
    cat "$EXISTING_LOG" >&2
    exit 1
fi

if [ "$(<"$EXISTING_ROOT/demo/project/demo.txt")" != $'base\nexisting' ]; then
    printf 'expected existing option to update existing file\n' >&2
    exit 1
fi

RESTORE_LOG="$TMP_DIR/restore.log"
(
    cd "$RESTORE_ROOT"
    "$SERIES_ROOT/apply.sh" --mb
) >"$RESTORE_LOG" 2>&1

if ! grep -q 'Selected patch option: demo/project source-shape restore' "$RESTORE_LOG"; then
    printf 'expected restore option selection\n' >&2
    cat "$RESTORE_LOG" >&2
    exit 1
fi

if [ "$(<"$RESTORE_ROOT/demo/project/demo.txt")" != $'base\nrestored' ]; then
    printf 'expected restore option to create and update file\n' >&2
    exit 1
fi
