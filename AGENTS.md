# AGENTS.md

## Repo Shape
- This repo is a collection of `git am` patch series for an AOSP checkout, not a buildable workspace. Top-level paths like `frameworks/`, `hardware/`, `kernel/`, `packages/`, and `system/` mirror target project paths inside Android source.
- Each directory containing `*.patch` files is an independent series for the matching AOSP project.

## Workflow
- Run `./fuck-bpf/apply.sh --mb` from the root of the Android source tree. `apply.sh` uses the caller's current directory as the AOSP root.
- To apply one series manually, run `git am -3 /path/to/fuck-bpf/<project>/*.patch` from the matching project inside the AOSP checkout.
- `apply.sh` applies patches in shell-glob order, so keep numeric prefixes zero-padded and strictly increasing within a directory.

## Critical Gotcha
- `apply.sh` only applies patches when the first argument is exactly `--mb`.
- Any other invocation takes the cleanup branch: for every patch-bearing project it runs `git am --abort`, `git reset --hard`, and `git clean -fd` in the corresponding AOSP path.
- Never suggest or run `./apply.sh` casually against a populated tree unless destructive cleanup is intended.

## Patch Conventions
- Current patch-bearing project paths are `bionic`, `frameworks/native`, `hardware/interfaces`, `kernel/configs`, `packages/modules/Connectivity`, `packages/modules/DnsResolver`, `system/apex`, `system/bpf`, `system/core`, `system/netd`, `system/sepolicy`, and `system/vold`.
- Multi-patch series currently exist in `kernel/configs`, `packages/modules/Connectivity`, `system/bpf`, `system/core`, and `system/netd`; preserve series order when editing or inserting patches.
- `.pre-commit-config.yaml` enforces patch-specific rules: every patch must keep the mbox footer (`-- `), end with a trailing newline, avoid creating/modifying `*.patch` files inside the diff, and keep numbering increasing per directory.

## Verification
- There is no repo-local build or test suite here; practical verification is patch hygiene plus application against a real AOSP tree.
- For changed patches, run `pre-commit run --files path/to/changed.patch` or `pre-commit run --all-files`.
- If docs and scripts disagree, trust `apply.sh` and `.pre-commit-config.yaml` over README prose.
