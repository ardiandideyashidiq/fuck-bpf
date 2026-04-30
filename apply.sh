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

verify_series() {
    local series_dir="$1"
    local exit_code=0

    printf '== %s ==\n' "$series_dir"

    if [ -n "$(git -C "$AOSP_ROOT/$series_dir" status --short)" ]; then
        printf 'working tree not clean\n' >&2
        exit_code=1
    fi

    if git -C "$AOSP_ROOT/$series_dir" rev-parse --quiet --verify REBASE_HEAD > /dev/null; then
        printf 'git am still in progress\n' >&2
        exit_code=1
    else
        printf 'git am clean\n'
    fi

    return "$exit_code"
}

apply_series() {
    local series_dir="$1"
    local patch

    cd "$AOSP_ROOT/$series_dir"

    for patch in "$SCRIPT_DIR/$series_dir"/*.patch; do
        [ -e "$patch" ] || continue

        if git apply --reverse --check "$patch" > /dev/null 2>&1; then
            printf 'Skipping duplicate patch: %s\n' "${patch#$SCRIPT_DIR/}"
            continue
        fi

        git am -3 "$patch"
    done
}

dry_run_series() {
    local series_dir="$1"
    local patch
    local patch_rel
    local temp_worktree

    temp_worktree="$(mktemp -d /tmp/fuck-bpf-dry-run-XXXXXX)"
    git -C "$AOSP_ROOT/$series_dir" worktree add "$temp_worktree" HEAD > /dev/null

    for patch in "$SCRIPT_DIR/$series_dir"/*.patch; do
        [ -e "$patch" ] || continue
        patch_rel="${patch#$SCRIPT_DIR/}"

        if git -C "$temp_worktree" apply --reverse --check "$patch" > /dev/null 2>&1; then
            printf 'Skipping duplicate patch: %s\n' "$patch_rel"
            continue
        fi

        if git -C "$temp_worktree" am -3 "$patch" > /dev/null 2>&1; then
            printf 'Would apply patch: %s\n' "$patch_rel"
            continue
        fi

        git -C "$temp_worktree" am --abort > /dev/null 2>&1 || true
        git -C "$AOSP_ROOT/$series_dir" worktree remove --force "$temp_worktree" > /dev/null 2>&1 || true
        printf 'Would fail patch: %s\n' "$patch_rel" >&2
        return 1
    done

    git -C "$AOSP_ROOT/$series_dir" worktree remove --force "$temp_worktree" > /dev/null 2>&1 || true
    return 0
}

while IFS= read -r series_dir; do
    [ -n "$series_dir" ] || continue
    if [ "$MODE" = "--mb" ]; then
        apply_series "$series_dir"
    elif [ "$MODE" = "--dry-run" ]; then
        dry_run_series "$series_dir"
    elif [ "$MODE" = "--verify" ]; then
        verify_series "$series_dir"
    else
        cleanup_series "$series_dir"
    fi
done < <(list_patch_dirs)
