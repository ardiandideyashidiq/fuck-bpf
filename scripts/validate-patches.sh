#!/bin/bash

set -euo pipefail

SOURCE_ROOT="${1:-${FUCK_BPF_SOURCE_ROOT:-}}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

list_patch_dirs() {
    find "$SCRIPT_DIR" -name '*.patch' -exec dirname {} \; | sed "s#^$SCRIPT_DIR/##" | sort -u
}

if [ -z "$SOURCE_ROOT" ]; then
    printf 'Usage: scripts/validate-patches.sh <synced-source-root>\n' >&2
    exit 1
fi

if [ ! -d "$SOURCE_ROOT" ]; then
    printf 'Synced source root not found: %s\n' "$SOURCE_ROOT" >&2
    exit 1
fi

exit_code=0

while IFS= read -r series_dir; do
    [ -n "$series_dir" ] || continue

    if [ ! -d "$SOURCE_ROOT/$series_dir" ]; then
        printf 'Series missing source repo: %s\n' "$series_dir" >&2
        exit_code=1
        continue
    fi

    temp_worktree="$(mktemp -d /tmp/fuck-bpf-validate-XXXXXX)"
    git -C "$SOURCE_ROOT/$series_dir" worktree add "$temp_worktree" HEAD > /dev/null

    series_ok=1
    for patch in "$SCRIPT_DIR/$series_dir"/*.patch; do
        [ -e "$patch" ] || continue

        if git -C "$temp_worktree" apply --reverse --check "$patch" > /dev/null 2>&1; then
            continue
        fi

        if ! git -C "$temp_worktree" am -3 "$patch" > /dev/null 2>&1; then
            printf 'Series failed: %s\n' "$series_dir" >&2
            git -C "$temp_worktree" am --abort > /dev/null 2>&1 || true
            exit_code=1
            series_ok=0
            break
        fi
    done

    if [ "$series_ok" -eq 1 ]; then
        printf 'Series applies cleanly: %s\n' "$series_dir"
    fi

    git -C "$SOURCE_ROOT/$series_dir" worktree remove --force "$temp_worktree" > /dev/null 2>&1 || true
done < <(list_patch_dirs)

exit "$exit_code"
