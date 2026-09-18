"""The sync layer's copy of the guide skill's name must match the renderer's.

``skills/coffer-guide/`` is spelled twice in the product: once in
``application.knowledge.guide_render``, which writes the name into the skill's
own frontmatter, and once in ``infrastructure.sync.paths``, which is the set of
tree paths a converge round neither publishes nor applies (spec vault-sync
FR-093).

The duplication is forced, not careless. import-linter's cross-kind contracts
forbid the sync slice from importing ``coffer.application.knowledge`` *and*
``coffer.domain.skill``, in both directions, so there is no module both can
read — exactly as the knowledge and skill *roots* are resolved in the sync
slice rather than imported from the kinds that own them.

What the fence cannot force is that the two stay the same, and drift here is
silent and expensive: rename the skill, and the sync layer goes on excluding a
folder that no longer exists while the folder that does exist starts converging
again — which is the churn loop this whole rule exists to stop, back with
nothing on fire to show for it. A test may import both, so it does.
"""

from __future__ import annotations

from coffer.application.knowledge.guide_render import GUIDE_SKILL_NAME
from coffer.infrastructure.sync.paths import (
    NON_CONVERGING_TREE_PATHS,
    non_converging_tree_paths,
)


def test_the_guide_skill_folder_is_the_one_the_renderer_names() -> None:
    assert f"skills/{GUIDE_SKILL_NAME}/" in NON_CONVERGING_TREE_PATHS, (
        f"the sync layer excludes {sorted(NON_CONVERGING_TREE_PATHS)}, but the "
        f"generated skill is called {GUIDE_SKILL_NAME!r}. Rename it in "
        "infrastructure/sync/paths.py too, or the folder converges again."
    )


def test_every_excluded_path_is_a_directory_prefix() -> None:
    """The trailing slash is load-bearing.

    Both the mirror and the applier test membership with ``startswith``, so an
    entry without it would also match a sibling whose name merely starts the
    same way — ``skills/coffer-guidelines/`` would stop converging, silently,
    and only for whoever happened to name a skill that way.
    """
    for path in NON_CONVERGING_TREE_PATHS:
        assert path.endswith("/"), path
        assert not path.startswith("/"), path


def test_the_accessor_answers_with_the_constant() -> None:
    assert non_converging_tree_paths() == NON_CONVERGING_TREE_PATHS
