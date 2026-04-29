# AGENTS.md

## Repo Shape
- This repo is a patch collection for an Android source tree, not a buildable app/library workspace. The top-level directories (`frameworks/`, `hardware/`, `kernel/`, `packages/`, `system/`) mirror target paths inside an AOSP checkout.
- Treat each directory containing `*.patch` files as a `git am` series for the matching AOSP project path.

## Canonical Workflow
- Apply all patch series from the root of the Android source tree with `./fuck-bpf/apply.sh --mb`.
- Apply one component manually from the matching AOSP project with `git am /path/to/fuck-bpf/<component>/*.patch`.
- Keep patch filenames zero-padded and ordered. `apply.sh` applies each directory via shell glob order: `git am $LOCALDIR/$mb/*.patch -3`.

## Critical Gotcha
- `apply.sh` does **not** apply patches unless the first arg is exactly `--mb`.
- Running `apply.sh` with no args, or any arg other than `--mb`, triggers the cleanup branch: for every patch-bearing project it runs `git am --abort`, `git reset --hard`, and `git clean -fd` in the corresponding AOSP checkout path.
- Because of that cleanup logic, never tell users to "try `./apply.sh`" casually, and do not run it against a populated source tree unless destructive cleanup is intended.

## Verified Coverage
- Current patch roots: `frameworks/native`, `hardware/interfaces`, `kernel/configs`, `packages/modules/Connectivity`, `packages/modules/DnsResolver`, `system/apex`, `system/bpf`, `system/core`, `system/netd`, `system/vold`.
- `packages/modules/Connectivity` and `system/bpf` are multi-patch series; preserve numbering and series order when editing or adding patches.

## Validation
- There is no repo-local build, test, lint, CI, or formatter config to run here.
- Practical verification in this repo is limited to checking patch formatting and ensuring each series applies cleanly with `git am` against the intended Android tree.
- Trust `apply.sh` and the patch files over README prose if they conflict.
