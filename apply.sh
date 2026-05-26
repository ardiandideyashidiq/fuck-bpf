#!/bin/bash

set -euo pipefail

MODE="${1:-}"
AOSP_ROOT="$(pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_FILE="$AOSP_ROOT/.fuck-bpf-apply-state"
MANIFEST_NAME=".fuck-bpf-series"
FAILED_PATCHES=()

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
    {
        find "$SCRIPT_DIR" -name '*.patch' -exec dirname {} \;
        find "$SCRIPT_DIR" -name "$MANIFEST_NAME" -exec dirname {} \;
    } | sed "s#^$SCRIPT_DIR/##" | sort -u
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

    FAILED_PATCHES+=("$patch_rel")
}

print_regeneration_summary() {
    local failed

    [ "${#FAILED_PATCHES[@]}" -eq 0 ] && return 0

    printf 'Patches needing regeneration:\n' >&2
    for failed in "${FAILED_PATCHES[@]}"; do
        printf 'Patch needs regeneration: %s\n' "$failed" >&2
    done

    return 1
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

patch_rel_path() {
    local series_dir="$1"
    local patch_name="$2"

    printf '%s/%s\n' "$series_dir" "$patch_name"
}

patch_abs_path() {
    local series_dir="$1"
    local patch_name="$2"

    printf '%s/%s/%s\n' "$SCRIPT_DIR" "$series_dir" "$patch_name"
}

run_patch_on_repo() {
    local series_dir="$1"
    local repo_dir="$2"
    local patch_name="$3"
    local mode="$4"
    local patch
    local patch_rel

    patch="$(patch_abs_path "$series_dir" "$patch_name")"
    patch_rel="$(patch_rel_path "$series_dir" "$patch_name")"

    if [ ! -f "$patch" ]; then
        print_patch_needs_regeneration "$patch_rel"
        return 1
    fi

    if is_patch_already_applied "$repo_dir" "$patch" "$series_dir"; then
        if [ "$mode" != "probe" ]; then
            printf 'Skipping duplicate patch: %s\n' "$patch_rel"
        fi
        return 0
    fi

    if git -C "$repo_dir" am -3 "$patch" > /dev/null 2>&1; then
        if [ "$mode" = "apply" ]; then
            printf 'Applied patch: %s\n' "$patch_rel"
        elif [ "$mode" = "dry-run" ]; then
            printf 'Would apply patch: %s\n' "$patch_rel"
        fi
        return 0
    fi

    git -C "$repo_dir" am --abort > /dev/null 2>&1 || true
    if [ "$mode" != "probe" ]; then
        print_patch_needs_regeneration "$patch_rel"
    fi
    return 1
}

run_patch_sequence_on_repo() {
    local series_dir="$1"
    local repo_dir="$2"
    local mode="$3"
    local patch_name
    shift 3

    for patch_name in "$@"; do
        if ! run_patch_on_repo "$series_dir" "$repo_dir" "$patch_name" "$mode"; then
            return 1
        fi
    done

    return 0
}

probe_patch_option() {
    local series_dir="$1"
    local repo_dir="$2"
    local temp_worktree
    local result=0
    shift 2

    temp_worktree="$(mktemp -d /tmp/fuck-bpf-option-XXXXXX)"
    git -C "$repo_dir" worktree add "$temp_worktree" HEAD > /dev/null

    if ! run_patch_sequence_on_repo "$series_dir" "$temp_worktree" "probe" "$@"; then
        result=1
    fi

    git -C "$temp_worktree" am --abort > /dev/null 2>&1 || true
    git -C "$repo_dir" worktree remove --force "$temp_worktree" > /dev/null 2>&1 || true
    return "$result"
}

run_patch_choice() {
    local series_dir="$1"
    local repo_dir="$2"
    local mode="$3"
    local choice_name="$4"
    local option_line
    local option_name
    local option_patches
    shift 4

    for option_line in "$@"; do
        option_name="${option_line%% *}"
        option_patches="${option_line#* }"

        # shellcheck disable=SC2086
        if probe_patch_option "$series_dir" "$repo_dir" $option_patches; then
            printf 'Selected patch option: %s %s %s\n' "$series_dir" "$choice_name" "$option_name"
            # shellcheck disable=SC2086
            run_patch_sequence_on_repo "$series_dir" "$repo_dir" "$mode" $option_patches
            return $?
        fi
    done

    print_patch_needs_regeneration "$series_dir/$choice_name"
    return 1
}

trim_manifest_line() {
    local line="$1"

    line="${line%%#*}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    printf '%s\n' "$line"
}

run_manifest_series() {
    local series_dir="$1"
    local repo_dir="$2"
    local mode="$3"
    local manifest="$SCRIPT_DIR/$series_dir/$MANIFEST_NAME"
    local line
    local keyword
    local choice_name=""
    local in_choice=0
    local options=()

    while IFS= read -r line || [ -n "$line" ]; do
        line="$(trim_manifest_line "$line")"
        [ -z "$line" ] && continue

        keyword="${line%% *}"
        if [ "$in_choice" -eq 1 ]; then
            if [ "$keyword" = "option" ]; then
                options+=("${line#option }")
                continue
            fi
            if [ "$keyword" = "endchoice" ]; then
                if ! run_patch_choice "$series_dir" "$repo_dir" "$mode" "$choice_name" "${options[@]}"; then
                    return 1
                fi
                in_choice=0
                choice_name=""
                options=()
                continue
            fi
            printf 'Invalid manifest line in choice %s: %s\n' "$manifest" "$line" >&2
            return 1
        fi

        if [ "$keyword" = "patch" ]; then
            if ! run_patch_on_repo "$series_dir" "$repo_dir" "${line#patch }" "$mode"; then
                return 1
            fi
        elif [ "$keyword" = "choice" ]; then
            in_choice=1
            choice_name="${line#choice }"
            options=()
        else
            printf 'Invalid manifest line in %s: %s\n' "$manifest" "$line" >&2
            return 1
        fi
    done < "$manifest"

    if [ "$in_choice" -eq 1 ]; then
        printf 'Unclosed choice in %s: %s\n' "$manifest" "$choice_name" >&2
        return 1
    fi

    return 0
}

run_glob_series() {
    local series_dir="$1"
    local repo_dir="$2"
    local mode="$3"
    local patch

    for patch in "$SCRIPT_DIR/$series_dir"/*.patch; do
        [ -e "$patch" ] || continue
        if ! run_patch_on_repo "$series_dir" "$repo_dir" "$(basename "$patch")" "$mode"; then
            return 1
        fi
    done

    return 0
}

run_series_steps() {
    local series_dir="$1"
    local repo_dir="$2"
    local mode="$3"

    if [ -f "$SCRIPT_DIR/$series_dir/$MANIFEST_NAME" ]; then
        run_manifest_series "$series_dir" "$repo_dir" "$mode"
        return $?
    fi

    run_glob_series "$series_dir" "$repo_dir" "$mode"
}

apply_series() {
    local series_dir="$1"

    record_series_base "$series_dir"
    run_series_steps "$series_dir" "$AOSP_ROOT/$series_dir" "apply"
}

dry_run_series() {
    local series_dir="$1"
    local temp_worktree

    temp_worktree="$(mktemp -d /tmp/fuck-bpf-dry-run-XXXXXX)"
    git -C "$AOSP_ROOT/$series_dir" worktree add "$temp_worktree" HEAD > /dev/null

    if ! run_series_steps "$series_dir" "$temp_worktree" "dry-run"; then
        git -C "$temp_worktree" am --abort > /dev/null 2>&1 || true
        git -C "$AOSP_ROOT/$series_dir" worktree remove --force "$temp_worktree" > /dev/null 2>&1 || true
        return 1
    fi

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
        apply_series "$series_dir" || true
    elif [ "$MODE" = "--dry-run" ]; then
        dry_run_series "$series_dir" || true
    elif [ "$MODE" = "--verify" ]; then
        verify_series "$series_dir"
    elif [ "$MODE" = "--cleanup" ]; then
        cleanup_series_fallback "$series_dir"
    else
        usage >&2
        exit 1
    fi
done < <(list_patch_dirs)

print_regeneration_summary
