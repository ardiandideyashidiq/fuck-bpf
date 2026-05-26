#!/bin/bash

set -euo pipefail

MODE="${1:-}"
AOSP_ROOT="$(pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_FILE="$AOSP_ROOT/.fuck-bpf-apply-state"

usage() {
    cat <<EOF
Usage: ./fuck-bpf/apply.sh [--mb|--dry-run|--verify|--cleanup]

  --mb       Apply all patch series
  --dry-run  Check whether all series would apply cleanly
  --verify   Check target repos for clean worktrees and am state
  --cleanup  Abort am sessions and reset target repos destructively
EOF
}

list_patch_dirs() {
    find "$SCRIPT_DIR" -name '*.patch' -exec dirname {} \; | sed "s#^$SCRIPT_DIR/##" | sort -u
}

state_has_series() {
    local series_dir="$1"

    [ -f "$STATE_FILE" ] && grep -Fq "$series_dir " "$STATE_FILE"
}

record_series_base() {
    local series_dir="$1"
    local head

    state_has_series "$series_dir" && return 0

    head="$(git -C "$AOSP_ROOT/$series_dir" rev-parse HEAD)"
    printf '%s %s\n' "$series_dir" "$head" >> "$STATE_FILE"
}

cleanup_series_to_base() {
    local series_dir="$1"
    local base="$2"

    if ! git -C "$AOSP_ROOT/$series_dir" cat-file -e "$base^{commit}" > /dev/null 2>&1; then
        printf 'cleanup base commit missing for %s: %s\n' "$series_dir" "$base" >&2
        return 1
    fi

    cleanup_series_worktree "$series_dir" "$base"
}

cleanup_series_worktree() {
    local series_dir="$1"
    local reset_target="${2:-HEAD}"

    printf 'Cleaning %s to %s\n' "$series_dir" "$reset_target"
    git -C "$AOSP_ROOT/$series_dir" am --abort > /dev/null 2>&1 || true
    git -C "$AOSP_ROOT/$series_dir" reset --hard "$reset_target" > /dev/null
    git -C "$AOSP_ROOT/$series_dir" clean -ffdx > /dev/null
}

patch_id_for_file() {
    local patch="$1"

    git patch-id --stable < "$patch" | awk '{print $1}'
}

patch_id_for_commit_in_repo() {
    local repo_dir="$1"
    local commit="$2"

    git -C "$repo_dir" show --format= "$commit" | git patch-id --stable | awk '{print $1}'
}

is_patch_commit_in_repo() {
    local repo_dir="$1"
    local patch="$2"
    local commit="$3"
    local commit_patch_id
    local patch_patch_id

    commit_patch_id="$(patch_id_for_commit_in_repo "$repo_dir" "$commit")"
    patch_patch_id="$(patch_id_for_file "$patch")"

    if [ -n "$commit_patch_id" ] && [ -n "$patch_patch_id" ]; then
        [ "$commit_patch_id" = "$patch_patch_id" ]
        return $?
    fi

    return 1
}

print_patch_needs_regeneration() {
    local patch_rel="$1"

    printf 'Patch needs regeneration: %s\n' "$patch_rel" >&2
}

is_series_patch_commit() {
    local series_dir="$1"
    local commit="$2"

    is_series_patch_commit_in_repo "$AOSP_ROOT/$series_dir" "$series_dir" "$commit"
}

is_series_patch_commit_in_repo() {
    local repo_dir="$1"
    local series_dir="$2"
    local commit="$3"
    local patch

    for patch in "$SCRIPT_DIR/$series_dir"/*.patch; do
        [ -e "$patch" ] || continue

        if is_patch_commit_in_repo "$repo_dir" "$patch" "$commit"; then
            return 0
        fi
    done

    return 1
}

is_patch_already_applied() {
    local repo_dir="$1"
    local patch="$2"
    local series_dir="$3"
    local commit
    local saw_non_series_commit=0

    if git -C "$repo_dir" apply --reverse --check "$patch" > /dev/null 2>&1; then
        return 0
    fi

    for commit in $(git -C "$repo_dir" rev-list --max-count=200 HEAD); do
        if is_patch_commit_in_repo "$repo_dir" "$patch" "$commit"; then
            if [ "$saw_non_series_commit" -eq 0 ]; then
                return 0
            fi
            return 1
        fi
        if ! is_series_patch_commit_in_repo "$repo_dir" "$series_dir" "$commit"; then
            saw_non_series_commit=1
        fi
    done

    return 1
}

cleanup_series_fallback() {
    local series_dir="$1"
    local commit
    local matched_count=0
    local scanned_count=0

    printf 'Using fallback cleanup for %s\n' "$series_dir"
    git -C "$AOSP_ROOT/$series_dir" am --abort > /dev/null 2>&1 || true

    while true; do
        commit="$(git -C "$AOSP_ROOT/$series_dir" rev-parse HEAD)"
        if ! is_series_patch_commit "$series_dir" "$commit"; then
            break
        fi
        matched_count=$((matched_count + 1))
        git -C "$AOSP_ROOT/$series_dir" reset --hard HEAD~1 > /dev/null
    done

    if [ "$matched_count" -eq 0 ]; then
        for commit in $(git -C "$AOSP_ROOT/$series_dir" rev-list --max-count=50 HEAD); do
            scanned_count=$((scanned_count + 1))
            if is_series_patch_commit "$series_dir" "$commit"; then
                printf 'refusing cleanup for %s: non-patch commit is above applied patch commit\n' "$series_dir" >&2
                return 1
            fi
        done
        [ "$scanned_count" -gt 0 ] || true
    fi

    cleanup_series_worktree "$series_dir"
}

cleanup_from_state() {
    local series_dir
    local base
    local exit_code=0

    while read -r series_dir base; do
        [ -n "$series_dir" ] || continue
        printf 'Using recorded cleanup state for %s\n' "$series_dir"
        if ! cleanup_series_to_base "$series_dir" "$base"; then
            exit_code=1
        fi
    done < "$STATE_FILE"

    if [ "$exit_code" -eq 0 ]; then
        rm -f "$STATE_FILE"
    fi

    return "$exit_code"
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

    record_series_base "$series_dir"

    cd "$AOSP_ROOT/$series_dir"

    for patch in "$SCRIPT_DIR/$series_dir"/*.patch; do
        [ -e "$patch" ] || continue

        if is_patch_already_applied "$AOSP_ROOT/$series_dir" "$patch" "$series_dir"; then
            printf 'Skipping duplicate patch: %s\n' "${patch#$SCRIPT_DIR/}"
            continue
        fi

        if ! git am -3 "$patch"; then
            print_patch_needs_regeneration "${patch#$SCRIPT_DIR/}"
            return 1
        fi
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

        if is_patch_already_applied "$temp_worktree" "$patch" "$series_dir"; then
            printf 'Skipping duplicate patch: %s\n' "$patch_rel"
            continue
        fi

        if git -C "$temp_worktree" am -3 "$patch" > /dev/null 2>&1; then
            printf 'Would apply patch: %s\n' "$patch_rel"
            continue
        fi

        git -C "$temp_worktree" am --abort > /dev/null 2>&1 || true
        git -C "$AOSP_ROOT/$series_dir" worktree remove --force "$temp_worktree" > /dev/null 2>&1 || true
        print_patch_needs_regeneration "$patch_rel"
        return 1
    done

    git -C "$AOSP_ROOT/$series_dir" worktree remove --force "$temp_worktree" > /dev/null 2>&1 || true
    return 0
}

if [ "$MODE" = "--cleanup" ] && [ -f "$STATE_FILE" ]; then
    cleanup_from_state
    exit $?
fi

while IFS= read -r series_dir; do
    [ -n "$series_dir" ] || continue
    if [ "$MODE" = "--mb" ]; then
        apply_series "$series_dir"
    elif [ "$MODE" = "--dry-run" ]; then
        dry_run_series "$series_dir"
    elif [ "$MODE" = "--verify" ]; then
        verify_series "$series_dir"
    elif [ "$MODE" = "--cleanup" ]; then
        cleanup_series_fallback "$series_dir"
    else
        usage >&2
        exit 1
    fi
done < <(list_patch_dirs)
