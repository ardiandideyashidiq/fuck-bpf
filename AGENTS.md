# Repository Guidelines

## Project Structure & Module Organization

This repository stores `git am` patch series for an Android/AOSP source tree. It is not a standalone buildable project. Top-level directories mirror target AOSP projects, such as `bionic/`, `frameworks/native/`, `packages/modules/Connectivity/`, `system/bpf/`, and `system/netd/`.

Each directory containing `*.patch` files is an independent series for the matching AOSP project. Multi-patch series must remain in strict numeric order, for example `system/bpf/0001-...patch` before `system/bpf/0002-...patch`. Python modules live in `scripts/`; tests live in `tests/`.

## Build, Test, and Development Commands

- `./fuck-bpf/apply.py --mb`: run from the root of a synced AOSP checkout to apply every patch series.
- `./fuck-bpf/apply.py --dry-run`: check whether patch series would apply cleanly without mutating target repos.
- `./fuck-bpf/apply.py --verify`: check target repos for clean worktrees and unfinished `git am` state.
- `./fuck-bpf/apply.py -v --dry-run`: verbose output during dry-run.
- `./fuck-bpf/apply.py --log-format json --cleanup`: structured JSON logging for CI.
- `pre-commit run --files path/to/changed.patch`: run patch hygiene checks for selected patches.
- `FUCK_BPF_SOURCE_ROOT=/path/to/aosp pre-commit run --all-files`: additionally validate patch replay against a synced source tree.

Use `./fuck-bpf/apply.py --cleanup` only when destructive cleanup is intended; it may abort `git am`, reset repos, and remove untracked files.

## Coding Style & Naming Conventions

Patch filenames must begin with zero-padded, increasing numeric prefixes: `0001-short-subject.patch`. Keep patch subjects descriptive and scoped to the target project. Do not create or modify `*.patch` files inside another patch diff.

Python scripts target Python 3.10+ and use stdlib only (no external dependencies beyond git). Use `argparse` for CLI, `logging` for structured output, and `subprocess` for git operations.

## Testing Guidelines

There is no repo-local Android build. Practical verification is patch hygiene plus replay against a real AOSP tree. Run targeted pre-commit checks after editing patches, and use `--dry-run` or `scripts/validate.py` with `FUCK_BPF_SOURCE_ROOT` when an AOSP checkout is available.

Tests use pytest and live in `tests/`. Run `uv run pytest` from the repo root. Unit tests mock git operations; integration tests create real temp git repos.

Lint and format with `uv run ruff check` and `uv run ruff format`. Ruff configuration is in `pyproject.toml`.

## Commit & Pull Request Guidelines

Recent commits use short, imperative summaries, sometimes terse. Prefer clearer messages such as `refactor apply script` or `regen hotspot patch`; include the affected series when useful.

Pull requests should describe which patch series changed, why the change is needed, and what verification was run. Mention any AOSP branch or device assumptions. Include failure output only when it helps reviewers reproduce the issue.

## Agent-Specific Instructions

Trust `apply.py` and `.pre-commit-config.yaml` over README prose if behavior differs. Preserve user changes in the worktree, avoid casual cleanup commands, and keep patch numbering stable when inserting or regenerating series.
