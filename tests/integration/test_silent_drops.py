import subprocess
from pathlib import Path

from .conftest import run_apply


def _commit(target: Path, filename: str, content: str, msg: str) -> None:
    (target / filename).write_text(content)
    subprocess.run(["git", "add", filename], cwd=target, capture_output=True, check=True)
    subprocess.run(
        ["git", "-c", "user.name=T", "-c", "user.email=t@t", "commit", "-m", msg],
        cwd=target,
        capture_output=True,
        check=True,
    )


def _format_patch(target: Path) -> str:
    return subprocess.run(
        ["git", "format-patch", "-1", "HEAD", "--stdout"],
        cwd=target,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def test_patch_that_never_applies_is_named_in_report(
    integration_env: tuple[Path, Path, Path],
) -> None:
    """A series must never report success for a patch it did not apply.

    Regression: SERIES_STATS only carried counts, so a patch that landed in
    "skipped" with its change absent from the tree left the run looking clean
    while silently dropping part of the series.
    """
    aosp_root, series_root, target = integration_env
    patch_dir = series_root / "demo" / "project"

    _commit(target, "demo.txt", "hello\n", "first")
    (patch_dir / "0001-first.patch").write_text(_format_patch(target))

    # A second patch that will never apply: it expects a file the tree lacks.
    (patch_dir / "0002-gone.patch").write_text(
        "From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001\n"
        "From: T <t@t>\n"
        "Subject: [PATCH] gone\n"
        "\n"
        "---\n"
        " never-there.txt | 1 +\n"
        " 1 file changed, 1 insertion(+)\n"
        "\n"
        "diff --git a/never-there.txt b/never-there.txt\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/never-there.txt\n"
        "@@ -0,0 +1 @@\n"
        "+content\n"
        "-- \n"
        "2.40.0\n"
    )

    run_apply(series_root, aosp_root, "--mb")
    proc = run_apply(series_root, aosp_root, "--mb")

    combined = proc.stdout + proc.stderr
    # The patch that cannot apply must be named as a problem, not folded into
    # a bare "N skipped" count.
    assert "0002-gone.patch" in combined
    assert "Patches needing regeneration" in combined or "not needed" in combined or "never applied" in combined, (
        combined
    )


def test_skipped_patches_are_listed_by_name(
    integration_env: tuple[Path, Path, Path],
) -> None:
    aosp_root, series_root, target = integration_env
    patch_dir = series_root / "demo" / "project"

    _commit(target, "demo.txt", "hello\n", "first")
    (patch_dir / "0001-first.patch").write_text(_format_patch(target))

    run_apply(series_root, aosp_root, "--mb")
    proc = run_apply(series_root, aosp_root, "--mb")

    combined = proc.stdout + proc.stderr
    assert "0001-first.patch" in combined


def test_failing_patch_names_the_patches_after_it(
    integration_env: tuple[Path, Path, Path],
) -> None:
    """When a series stops, the patches it never reached are reported."""
    aosp_root, series_root, target = integration_env
    patch_dir = series_root / "demo" / "project"

    # Modify a line that does not exist: neither a clean apply nor a
    # reverse-apply, so this patch cannot be reconciled and stops the series.
    (patch_dir / "0001-broken.patch").write_text(
        "From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001\n"
        "From: T <t@t>\n"
        "Subject: [PATCH] broken\n"
        "\n"
        "---\n"
        " absent.txt | 3 ++-\n"
        " 1 file changed, 2 insertions(+), 1 deletion(-)\n"
        "\n"
        "diff --git a/absent.txt b/absent.txt\n"
        "--- a/absent.txt\n"
        "+++ b/absent.txt\n"
        "@@ -1,3 +1,4 @@\n"
        " line one\n"
        "-line two that is not there\n"
        "+line two replaced\n"
        " line three\n"
        "+line four\n"
        "-- \n"
        "2.40.0\n"
    )
    (patch_dir / "0002-never-reached.patch").write_text(
        "From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001\n"
        "From: T <t@t>\n"
        "Subject: [PATCH] never reached\n"
        "\n"
        "---\n"
        " other.txt | 1 +\n"
        " 1 file changed, 1 insertion(+)\n"
        "\n"
        "diff --git a/other.txt b/other.txt\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/other.txt\n"
        "@@ -0,0 +1 @@\n"
        "+y\n"
        "-- \n"
        "2.40.0\n"
    )
    # No manifest: run_glob_series walks the patches in order and stops at the
    # first failure, so 0002 is never even attempted.
    proc = run_apply(series_root, aosp_root, "--mb")
    combined = proc.stdout + proc.stderr
    assert "0001-broken.patch" in combined
    assert "never reached" in combined or "0002-never-reached.patch" in combined


def test_dry_run_does_not_report_unreached_patches(
    integration_env: tuple[Path, Path, Path],
) -> None:
    """A dry-run scratch worktree must not claim patches were dropped.

    Regression: the dry-run and the choice-probe both run series steps in a
    throwaway worktree, where an apply failure says nothing about the real
    tree. Reporting them as "never applied" buried the real signal.
    """
    aosp_root, series_root, target = integration_env
    patch_dir = series_root / "demo" / "project"

    _commit(target, "demo.txt", "hello\n", "first")
    (patch_dir / "0001-first.patch").write_text(_format_patch(target))

    (patch_dir / "0002-broken.patch").write_text(
        "From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001\n"
        "From: T <t@t>\n"
        "Subject: [PATCH] broken\n"
        "\n"
        "---\n"
        " absent.txt | 3 ++-\n"
        " 1 file changed, 2 insertions(+), 1 deletion(-)\n"
        "\n"
        "diff --git a/absent.txt b/absent.txt\n"
        "--- a/absent.txt\n"
        "+++ b/absent.txt\n"
        "@@ -1,3 +1,4 @@\n"
        " line one\n"
        "-line two that is not there\n"
        "+line two replaced\n"
        " line three\n"
        "+line four\n"
        "-- \n"
        "2.40.0\n"
    )
    (patch_dir / "0003-after.patch").write_text(
        "From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001\n"
        "From: T <t@t>\n"
        "Subject: [PATCH] after\n"
        "\n"
        "---\n"
        " other.txt | 1 +\n"
        " 1 file changed, 1 insertion(+)\n"
        "\n"
        "diff --git a/other.txt b/other.txt\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/other.txt\n"
        "@@ -0,0 +1 @@\n"
        "+y\n"
        "-- \n"
        "2.40.0\n"
    )

    proc = run_apply(series_root, aosp_root, "--dry-run")
    combined = proc.stdout + proc.stderr
    assert "never applied" not in combined, combined
    # The real tree is untouched by a dry-run.
    assert not (target / "other.txt").exists()


def test_no_change_am_is_reported_as_duplicate(
    integration_env: tuple[Path, Path, Path],
) -> None:
    """`git am` exits 0 with "No changes" when the patch is already in the tree.

    Regression: that was logged as "Applied patch" even though nothing was
    committed, so a patch that could never apply again looked like it landed
    on every single run.
    """
    aosp_root, series_root, target = integration_env
    patch_dir = series_root / "demo" / "project"

    # Capture the patch, then leave the change committed in the tree. The
    # patch is already present, so `git am -3` reports "No changes" and exits 0.
    _commit(target, "demo.txt", "hello\n", "first")
    patch = patch_dir / "0001-first.patch"
    patch.write_text(_format_patch(target))

    head_before = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=target, capture_output=True, text=True, check=True
    ).stdout.strip()

    proc = run_apply(series_root, aosp_root, "--mb")
    head_after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=target, capture_output=True, text=True, check=True
    ).stdout.strip()

    assert head_after == head_before, "a duplicate must not create a commit"
    assert "Applied patch:" not in proc.stderr, proc.stderr
    assert "Skipping duplicate patch:" in proc.stderr, proc.stderr
