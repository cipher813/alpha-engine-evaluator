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


def test_every_repo_tree_reader_declares_itself():
    """A module reading an image-absent repo path declares that on the MODULE.

    Two declarations are accepted, because they are not interchangeable:

    * ``pytestmark = pytest.mark.repo_tree`` -- the whole module is repo-tree,
      and a missing file in the repo context is a LOUD failure. Preferred.
    * a module-level ``pytest.skip`` / ``skipif`` keyed on the path's absence --
      for a module that is only PARTLY repo-tree (some of its assertions do
      hold against the shipped package and are worth running in the image).
      Weaker: it also goes quiet if the file is genuinely deleted.

    What is NOT accepted is neither -- that is the shape that reddened main on
    2026-09-08. Unifying the second form onto the marker is tracked separately.
    """
    unmarked = []
    for path in sorted((REPO_ROOT / "tests").glob("test_*.py")):
        src = path.read_text()
        if f"pytest.mark.{MARKER}" in src:
            continue
        if not re.search(
            r"/\s*\"(\.github|infrastructure|Dockerfile|console\.descriptor\.yaml)\"",
            src,
        ):
            continue
        if re.search(r"pytest\.(skip|mark\.skipif)\(", src):
            continue
        unmarked.append(path.name)
    assert not unmarked, (
        "these modules read a repository path the built image does not carry "
        f"but neither carry `pytest.mark.{MARKER}` nor a module-level "
        "image-context skip, so docker-image-tests will fail on them: "
        f"{unmarked} (alpha-engine-config-I10257)"
    )
