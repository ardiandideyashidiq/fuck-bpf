#!/bin/bash

set -euo pipefail

SOURCE_ROOT="${1:-${FUCK_BPF_SOURCE_ROOT:-}}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST_NAME=".fuck-bpf-series"
FAILED_PATCHES=()

list_patch_dirs() {
    {
        find "$SCRIPT_DIR" -name '*.patch' -exec dirname {} \;
        find "$SCRIPT_DIR" -name "$MANIFEST_NAME" -exec dirname {} \;
    } | sed "s#^$SCRIPT_DIR/##" | sort -u
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

    [ -n "$commit_patch_id" ] && [ -n "$patch_patch_id" ] && [ "$commit_patch_id" = "$patch_patch_id" ]
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
            [ "$saw_non_series_commit" -eq 0 ]
            return $?
        fi
        if ! is_series_patch_commit_in_repo "$repo_dir" "$series_dir" "$commit"; then
            saw_non_series_commit=1
        fi
    done

    return 1
}

record_regeneration() {
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

    patch="$(patch_abs_path "$series_dir" "$patch_name")"
    if [ ! -f "$patch" ]; then
        record_regeneration "$series_dir/$patch_name"
        return 1
    fi

    if is_patch_already_applied "$repo_dir" "$patch" "$series_dir"; then
        return 0
    fi

    if git -C "$repo_dir" am -3 "$patch" > /dev/null 2>&1; then
        return 0
    fi

    git -C "$repo_dir" am --abort > /dev/null 2>&1 || true
    if [ "$mode" != "probe" ]; then
        record_regeneration "$series_dir/$patch_name"
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

    temp_worktree="$(mktemp -d /tmp/fuck-bpf-validate-option-XXXXXX)"
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
    local choice_name="$3"
    local option_line
    local option_patches
    shift 3

    for option_line in "$@"; do
        option_patches="${option_line#* }"
        # shellcheck disable=SC2086
        if probe_patch_option "$series_dir" "$repo_dir" $option_patches; then
            # shellcheck disable=SC2086
            run_patch_sequence_on_repo "$series_dir" "$repo_dir" "validate" $option_patches
            return $?
        fi
    done

    record_regeneration "$series_dir/$choice_name"
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
                if ! run_patch_choice "$series_dir" "$repo_dir" "$choice_name" "${options[@]}"; then
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
            if ! run_patch_on_repo "$series_dir" "$repo_dir" "${line#patch }" "validate"; then
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

    [ "$in_choice" -eq 0 ]
}

run_glob_series() {
    local series_dir="$1"
    local repo_dir="$2"
    local patch

    for patch in "$SCRIPT_DIR/$series_dir"/*.patch; do
        [ -e "$patch" ] || continue
        if ! run_patch_on_repo "$series_dir" "$repo_dir" "$(basename "$patch")" "validate"; then
            return 1
        fi
    done

    return 0
}

run_series() {
    local series_dir="$1"
    local repo_dir="$2"

    if [ -f "$SCRIPT_DIR/$series_dir/$MANIFEST_NAME" ]; then
        run_manifest_series "$series_dir" "$repo_dir"
        return $?
    fi

    run_glob_series "$series_dir" "$repo_dir"
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

    if run_series "$series_dir" "$temp_worktree"; then
        printf 'Series applies cleanly: %s\n' "$series_dir"
    else
        printf 'Series failed: %s\n' "$series_dir" >&2
        exit_code=1
    fi

    git -C "$temp_worktree" am --abort > /dev/null 2>&1 || true
    git -C "$SOURCE_ROOT/$series_dir" worktree remove --force "$temp_worktree" > /dev/null 2>&1 || true
done < <(list_patch_dirs)

if ! print_regeneration_summary; then
    exit_code=1
fi

exit "$exit_code"
