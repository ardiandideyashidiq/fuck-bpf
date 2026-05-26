#!/bin/bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

create_fixture() {
    local name="$1"
    local aosp_root="$TMP_DIR/$name/aosp"
    local series_root="$TMP_DIR/$name/fuck-bpf"
    local target_dir="$aosp_root/demo/project"
    local patch_dir="$series_root/demo/project"

    mkdir -p "$target_dir" "$patch_dir"
    cp "$REPO_ROOT/apply.sh" "$series_root/apply.sh"

    git init "$target_dir" >/dev/null
    printf 'hello\n' > "$target_dir/demo.txt"
    printf 'build/\nout/\n' > "$target_dir/.gitignore"
    git -C "$target_dir" add .gitignore demo.txt
    git -C "$target_dir" -c user.name='Test User' -c user.email='test@example.com' \
        commit -m 'base' >/dev/null

    printf '%s\n%s\n%s\n' "$aosp_root" "$series_root" "$target_dir"
}

create_patch() {
    local target_dir="$1"
    local patch_dir="$2"
    local patch_name="$3"
    local commit_message="$4"
    local content="$5"

    printf '%s\n' "$content" > "$target_dir/demo.txt"
    git -C "$target_dir" add demo.txt
    git -C "$target_dir" -c user.name='Test User' -c user.email='test@example.com' \
        commit -m "$commit_message" >/dev/null
    git -C "$target_dir" format-patch -1 HEAD --stdout > "$patch_dir/$patch_name"
}

create_build_artifact_patch() {
    local target_dir="$1"
    local patch_dir="$2"
    local patch_name="$3"

    printf 'tracked artifact\n' > "$target_dir/out"
    git -C "$target_dir" add -f out
    git -C "$target_dir" -c user.name='Test User' -c user.email='test@example.com' \
        commit -m 'add generated artifact' >/dev/null
    git -C "$target_dir" format-patch -1 HEAD --stdout > "$patch_dir/$patch_name"
}

mapfile -t FIXTURE < <(create_fixture "mode-safety")
AOSP_ROOT="${FIXTURE[0]}"
SERIES_ROOT="${FIXTURE[1]}"
TARGET_DIR="${FIXTURE[2]}"
PATCH_DIR="$SERIES_ROOT/demo/project"

create_patch "$TARGET_DIR" "$PATCH_DIR" "0001-update-demo.patch" "update demo" "hello world"
git -C "$TARGET_DIR" reset --hard HEAD~1 >/dev/null

printf 'dirty\n' >> "$TARGET_DIR/demo.txt"
mkdir -p "$TARGET_DIR/build"
printf 'generated\n' > "$TARGET_DIR/build/generated.txt"

NOARG_LOG="$TMP_DIR/noarg.log"
STATUS=0
(
    cd "$AOSP_ROOT"
    "$SERIES_ROOT/apply.sh"
) >"$NOARG_LOG" 2>&1 || STATUS=$?

if [ "$STATUS" -eq 0 ]; then
    printf 'expected no-arg apply.sh invocation to fail\n' >&2
    cat "$NOARG_LOG" >&2
    exit 1
fi

if ! grep -q 'Usage:' "$NOARG_LOG"; then
    printf 'expected usage output for no-arg invocation\n' >&2
    cat "$NOARG_LOG" >&2
    exit 1
fi

if [ "$(<"$TARGET_DIR/demo.txt")" != $'hello\ndirty' ]; then
    printf 'expected no-arg invocation to leave worktree untouched\n' >&2
    exit 1
fi

BADARG_LOG="$TMP_DIR/badarg.log"
STATUS=0
(
    cd "$AOSP_ROOT"
    "$SERIES_ROOT/apply.sh" --wat
) >"$BADARG_LOG" 2>&1 || STATUS=$?

if [ "$STATUS" -eq 0 ]; then
    printf 'expected unknown mode to fail\n' >&2
    cat "$BADARG_LOG" >&2
    exit 1
fi

if ! grep -q 'Usage:' "$BADARG_LOG"; then
    printf 'expected usage output for unknown mode\n' >&2
    cat "$BADARG_LOG" >&2
    exit 1
fi

if [ "$(<"$TARGET_DIR/demo.txt")" != $'hello\ndirty' ]; then
    printf 'expected unknown mode to leave worktree untouched\n' >&2
    exit 1
fi

(
    cd "$AOSP_ROOT"
    "$SERIES_ROOT/apply.sh" --cleanup
) >/dev/null

if [ "$(<"$TARGET_DIR/demo.txt")" != 'hello' ]; then
    printf 'expected fallback cleanup mode to restore dirty base tree\n' >&2
    exit 1
fi

if [ -e "$TARGET_DIR/build/generated.txt" ]; then
    printf 'expected cleanup mode to remove ignored generated files\n' >&2
    exit 1
fi

mapfile -t FIXTURE < <(create_fixture "ignored-path-conflict")
AOSP_ROOT="${FIXTURE[0]}"
SERIES_ROOT="${FIXTURE[1]}"
TARGET_DIR="${FIXTURE[2]}"
PATCH_DIR="$SERIES_ROOT/demo/project"
BASE_HEAD="$(git -C "$TARGET_DIR" rev-parse HEAD)"

create_build_artifact_patch "$TARGET_DIR" "$PATCH_DIR" "0001-add-generated-artifact.patch"
git -C "$TARGET_DIR" reset --hard "$BASE_HEAD" >/dev/null

mkdir -p "$TARGET_DIR/out"
printf 'stale generated artifact\n' > "$TARGET_DIR/out/generated.txt"

(
    cd "$AOSP_ROOT"
    "$SERIES_ROOT/apply.sh" --cleanup
) >/dev/null

if [ -e "$TARGET_DIR/out/generated.txt" ]; then
    printf 'expected cleanup to remove ignored directory before retrying patches\n' >&2
    exit 1
fi

(
    cd "$AOSP_ROOT"
    "$SERIES_ROOT/apply.sh" --mb
) >/dev/null

if [ "$(<"$TARGET_DIR/out")" != 'tracked artifact' ]; then
    printf 'expected cleanup to remove ignored blocker so the patch can apply\n' >&2
    exit 1
fi

mapfile -t FIXTURE < <(create_fixture "stateful-cleanup")
AOSP_ROOT="${FIXTURE[0]}"
SERIES_ROOT="${FIXTURE[1]}"
TARGET_DIR="${FIXTURE[2]}"
PATCH_DIR="$SERIES_ROOT/demo/project"
BASE_HEAD="$(git -C "$TARGET_DIR" rev-parse HEAD)"

create_patch "$TARGET_DIR" "$PATCH_DIR" "0001-update-demo.patch" "update demo" "hello world"
git -C "$TARGET_DIR" reset --hard "$BASE_HEAD" >/dev/null

(
    cd "$AOSP_ROOT"
    "$SERIES_ROOT/apply.sh" --mb
) >/dev/null

if [ "$(git -C "$TARGET_DIR" rev-parse HEAD)" = "$BASE_HEAD" ]; then
    printf 'expected --mb to apply a patch commit\n' >&2
    exit 1
fi

if [ ! -f "$AOSP_ROOT/.fuck-bpf-apply-state" ]; then
    printf 'expected --mb to record cleanup state\n' >&2
    exit 1
fi

(
    cd "$AOSP_ROOT"
    "$SERIES_ROOT/apply.sh" --cleanup
) >/dev/null

if [ "$(git -C "$TARGET_DIR" rev-parse HEAD)" != "$BASE_HEAD" ]; then
    printf 'expected stateful cleanup to reset to original base commit\n' >&2
    exit 1
fi

if [ -f "$AOSP_ROOT/.fuck-bpf-apply-state" ]; then
    printf 'expected successful cleanup to remove cleanup state\n' >&2
    exit 1
fi

mapfile -t FIXTURE < <(create_fixture "partial-failure")
AOSP_ROOT="${FIXTURE[0]}"
SERIES_ROOT="${FIXTURE[1]}"
TARGET_DIR="${FIXTURE[2]}"
PATCH_DIR="$SERIES_ROOT/demo/project"
BASE_HEAD="$(git -C "$TARGET_DIR" rev-parse HEAD)"

create_patch "$TARGET_DIR" "$PATCH_DIR" "0001-update-demo.patch" "update demo" "hello world"
git -C "$TARGET_DIR" reset --hard "$BASE_HEAD" >/dev/null
create_patch "$TARGET_DIR" "$PATCH_DIR" "0002-conflicting-demo.patch" "conflicting demo" "HELLO"
git -C "$TARGET_DIR" reset --hard "$BASE_HEAD" >/dev/null

STATUS=0
(
    cd "$AOSP_ROOT"
    "$SERIES_ROOT/apply.sh" --mb
) >/dev/null 2>&1 || STATUS=$?

if [ "$STATUS" -eq 0 ]; then
    printf 'expected --mb to fail on second conflicting patch\n' >&2
    exit 1
fi

if [ "$(git -C "$TARGET_DIR" rev-parse HEAD)" = "$BASE_HEAD" ]; then
    printf 'expected first patch commit to remain before cleanup\n' >&2
    exit 1
fi

(
    cd "$AOSP_ROOT"
    "$SERIES_ROOT/apply.sh" --cleanup
) >/dev/null

if [ "$(git -C "$TARGET_DIR" rev-parse HEAD)" != "$BASE_HEAD" ]; then
    printf 'expected cleanup after partial failure to restore base commit\n' >&2
    exit 1
fi

mapfile -t FIXTURE < <(create_fixture "legacy-fallback")
AOSP_ROOT="${FIXTURE[0]}"
SERIES_ROOT="${FIXTURE[1]}"
TARGET_DIR="${FIXTURE[2]}"
PATCH_DIR="$SERIES_ROOT/demo/project"
BASE_HEAD="$(git -C "$TARGET_DIR" rev-parse HEAD)"

create_patch "$TARGET_DIR" "$PATCH_DIR" "0001-update-demo.patch" "update demo" "hello world"
git -C "$TARGET_DIR" reset --hard "$BASE_HEAD" >/dev/null

git -C "$TARGET_DIR" am -3 "$PATCH_DIR/0001-update-demo.patch" >/dev/null

(
    cd "$AOSP_ROOT"
    "$SERIES_ROOT/apply.sh" --cleanup
) >/dev/null

if [ "$(git -C "$TARGET_DIR" rev-parse HEAD)" != "$BASE_HEAD" ]; then
    printf 'expected no-state fallback cleanup to drop matching patch commit\n' >&2
    exit 1
fi

mapfile -t FIXTURE < <(create_fixture "legacy-refuse-user-commit")
AOSP_ROOT="${FIXTURE[0]}"
SERIES_ROOT="${FIXTURE[1]}"
TARGET_DIR="${FIXTURE[2]}"
PATCH_DIR="$SERIES_ROOT/demo/project"
BASE_HEAD="$(git -C "$TARGET_DIR" rev-parse HEAD)"

create_patch "$TARGET_DIR" "$PATCH_DIR" "0001-update-demo.patch" "update demo" "hello world"
git -C "$TARGET_DIR" reset --hard "$BASE_HEAD" >/dev/null

git -C "$TARGET_DIR" am -3 "$PATCH_DIR/0001-update-demo.patch" >/dev/null
printf 'user work\n' > "$TARGET_DIR/user.txt"
git -C "$TARGET_DIR" add user.txt
git -C "$TARGET_DIR" -c user.name='Test User' -c user.email='test@example.com' \
    commit -m 'user commit' >/dev/null

REFUSE_LOG="$TMP_DIR/refuse.log"
STATUS=0
(
    cd "$AOSP_ROOT"
    "$SERIES_ROOT/apply.sh" --cleanup
) >"$REFUSE_LOG" 2>&1 || STATUS=$?

if [ "$STATUS" -eq 0 ]; then
    printf 'expected no-state cleanup to refuse deleting user commit\n' >&2
    cat "$REFUSE_LOG" >&2
    exit 1
fi

if ! grep -q 'refusing cleanup' "$REFUSE_LOG"; then
    printf 'expected refusal reason in cleanup log\n' >&2
    cat "$REFUSE_LOG" >&2
    exit 1
fi

if [ "$(git -C "$TARGET_DIR" log -1 --format=%s)" != 'user commit' ]; then
    printf 'expected refusal to preserve user commit at HEAD\n' >&2
    exit 1
fi
