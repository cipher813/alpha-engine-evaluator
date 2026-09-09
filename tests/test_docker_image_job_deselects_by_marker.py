"""`docker-image-tests` deselects repo-tree tests BY MARKER, never by a list.

alpha-engine-config-I10257. `ci.yml`'s `docker-image-tests` job mounts only
`tests/` into the built image, so a test asserting a property of the repository
tree (`.github/`, `infrastructure/`, `Dockerfile`, `console.descriptor.yaml`)
cannot resolve its inputs there. That exclusion used to be five `--ignore=`
flags hand-kept in the workflow -- a twin of a fact the test module already
knew, and one nobody updates when a sixth such module lands.

It was not updated. `crucible-evaluator#305` added
`tests/test_alert_message_lint_warn_only_survives_crash.py` (a `.github/`
reader) on 2026-09-08 and `main` went red the same day with three
`FileNotFoundError: /var/task/.github/workflows/alert-class-pr-guard.yml`,
blocking every open PR in this repo.

The declaration now lives on the module (`pytestmark = pytest.mark.repo_tree`)
and the job deselects the marker. This module keeps the workflow from drifting
back to a hand-kept list.
"""

from __future__ import annotations

import pathlib
import re
from pathlib import Path

import pytest

# Runs only where the repository tree exists. `ci.yml`'s `docker-image-tests`
# job mounts ONLY `tests/` into the built image, so this module's repo-root
# reads (`.github/`, `infrastructure/`, `Dockerfile`, `console.descriptor.yaml`)
# resolve to nothing there. Declared here rather than as an `--ignore=` flag in
# the workflow: the module is what knows (alpha-engine-config-I10257).
pytestmark = pytest.mark.repo_tree

REPO_ROOT = Path(__file__).resolve().parents[1]
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
CONFTEST = REPO_ROOT / "tests" / "conftest.py"
MARKER = "repo_tree"

# A path under the repository root that the built image does not carry. `tests/`
# is mounted and the application packages are COPYed, so those are absent here
# on purpose.
IMAGE_ABSENT_PATH = re.compile(
    r"""/\s*["'](\.github|infrastructure|scripts|Dockerfile|console\.descriptor\.yaml)["']"""
)

# `pytest.skip(...)` / `pytest.mark.skipif(...)` guarding on a path's absence --
# `.exists()`, `.is_file()`, `.is_dir()` -- the idiom I10258 retired.
ABSENCE_SKIP = re.compile(
    r"""pytest\.(?:skip|mark\.skipif)\(.{0,200}?\.(?:exists|is_file|is_dir)\(\)""",
    re.S,
)


def _docker_job_block() -> str:
    text = CI.read_text()
    start = text.index("  docker-image-tests:")
    rest = text[start + 1 :]
    end = re.search(r"\n  [a-z][a-z0-9-]*:\n", rest)
    return rest[: end.start()] if end else rest


def test_the_docker_job_deselects_the_marker():
    block = _docker_job_block()
    assert f"-m 'not {MARKER}'" in block, (
        "ci.yml's docker-image-tests job no longer deselects the "
        f"`{MARKER}` marker -- every repo-tree test will run inside the image, "
        "where the repository tree is not mounted, and fail with "
        "FileNotFoundError (alpha-engine-config-I10257)"
    )


def test_the_docker_job_carries_no_hand_kept_ignore_list():
    block = _docker_job_block()
    assert "--ignore=tests/" not in block, (
        "ci.yml's docker-image-tests job names individual test modules with "
        "`--ignore=` again. That list is a twin of a fact each module already "
        "declares, and it went stale once already (crucible-evaluator#305 "
        "reddened main on 2026-09-08). Mark the module "
        f"`pytestmark = pytest.mark.{MARKER}` instead "
        "(alpha-engine-config-I10257)"
    )


def test_the_marker_is_registered():
    assert f'"{MARKER}:' in CONFTEST.read_text(), (
        f"`{MARKER}` is not registered in tests/conftest.py's "
        "pytest_configure. An unregistered marker is a PytestUnknownMarkWarning, "
        "not an error, so a typo would silently deselect nothing"
    )


def test_every_repo_tree_reader_carries_the_marker():
    """A module reading an image-absent repo path declares it with the MARKER.

    One idiom, not two. An earlier revision also accepted a module-level
    ``pytest.skip`` / ``skipif`` keyed on the path's absence, because five
    modules used that form. They were converted in
    ``alpha-engine-config-I10258`` and the escape hatch is now gone.

    An absence-keyed skip cannot tell "the repository tree is not mounted, this
    is the image job" from "the file this test defends was deleted." In the
    second case the assertion disappears and nothing goes red. The marker
    separates them: the image job deselects it, and the repo-context job still
    fails loud on a missing file.
    """
    unmarked = []
    for path in sorted((REPO_ROOT / "tests").glob("test_*.py")):
        src = path.read_text()
        if f"pytest.mark.{MARKER}" in src:
            continue
        if not IMAGE_ABSENT_PATH.search(src):
            continue
        unmarked.append(path.name)
    assert not unmarked, (
        "these modules read a repository path the built image does not carry "
        f"but do not carry `pytest.mark.{MARKER}`, so docker-image-tests will "
        f"fail on them: {unmarked} (alpha-engine-config-I10257/-I10258)"
    )


def test_no_module_declares_itself_with_an_absence_keyed_skip():
    """The weaker idiom must not come back (alpha-engine-config-I10258)."""
    offenders = []
    for path in sorted((REPO_ROOT / "tests").glob("test_*.py")):
        # This module carries both patterns as regex SOURCE, not as behaviour.
        if path.name == pathlib.Path(__file__).name:
            continue
        src = path.read_text()
        if not IMAGE_ABSENT_PATH.search(src):
            continue
        if ABSENCE_SKIP.search(src):
            offenders.append(path.name)
    assert not offenders, (
        "these modules gate a repo-tree assertion on a file's ABSENCE "
        f"({offenders}). That also goes quiet when the file is genuinely "
        f"deleted. Use `pytest.mark.{MARKER}`, which the image job deselects "
        "and the repo-context job does not (alpha-engine-config-I10258)"
    )
