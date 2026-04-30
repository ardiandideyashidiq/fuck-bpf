#!/bin/bash

set -euo pipefail

MODE="${1:-}"
AOSP_ROOT="$(pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

list_patch_dirs() {
    find "$SCRIPT_DIR" -name '*.patch' -exec dirname {} \; | sed "s#^$SCRIPT_DIR/##" | sort -u
}

cleanup_series() {
    local series_dir="$1"

    cd "$AOSP_ROOT/$series_dir"
    git am --abort > /dev/null 2>&1 || true
    git reset --hard > /dev/null 2>&1
    git clean -fd > /dev/null 2>&1
}

apply_series() {
    local series_dir="$1"

    cd "$AOSP_ROOT/$series_dir"
    git am -3 "$SCRIPT_DIR/$series_dir"/*.patch
}

while IFS= read -r series_dir; do
    [ -n "$series_dir" ] || continue
    if [ "$MODE" = "--mb" ]; then
        apply_series "$series_dir"
    else
        cleanup_series "$series_dir"
    fi
done < <(list_patch_dirs)
