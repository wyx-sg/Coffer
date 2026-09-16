"""``render_digest`` — pure, no model, no filesystem (FR-032's mechanical
path). Every test here could run with no internal connection ever
configured, which is the entire point: the digest must be usable on its own.
"""

from __future__ import annotations

from coffer.application.memory.digest import render_digest
from coffer.domain.memory.fact import STATUS_SUPERSEDED, TYPE_FEEDBACK, TYPE_PROJECT, Fact, Origin


def _fact(**overrides: object) -> Fact:
    defaults: dict[str, object] = {
        "slug": "a-fact",
        "title": "A fact",
        "description": "A one-line description",
        "type": TYPE_PROJECT,
        "body": "The full body, never shown in a digest.",
        "partition": "coffer",
        "origins": (
            Origin(
                agent="claude_code",
                native_path="/home/dev/.claude/memory/a.md",
                captured_at="2026-09-01T00:00:00+00:00",
            ),
        ),
    }
    defaults.update(overrides)
    return Fact(**defaults)  # type: ignore[arg-type]


def test_groups_facts_by_type_with_one_line_each() -> None:
    project_fact = _fact(slug="p", title="Project fact", type=TYPE_PROJECT)
    feedback_fact = _fact(slug="f", title="Feedback fact", type=TYPE_FEEDBACK)

    text = render_digest([project_fact, feedback_fact], partition="coffer")

    assert "## Project" in text
    assert "## Feedback and standing instructions" in text
    assert "- **Project fact** — A one-line description" in text
    assert "- **Feedback fact** — A one-line description" in text
    # Project group must precede the feedback group (module's _TYPE_ORDER).
    assert text.index("Project fact") < text.index("Feedback fact")


def test_superseded_facts_are_omitted() -> None:
    active = _fact(slug="a", title="Still true")
    superseded = _fact(slug="b", title="No longer true", status=STATUS_SUPERSEDED)

    text = render_digest([active, superseded], partition="coffer")

    assert "Still true" in text
    assert "No longer true" not in text


def test_newest_first_within_a_type_group() -> None:
    older = _fact(
        slug="older",
        title="Older fact",
        origins=(
            Origin(agent="claude_code", native_path="/x", captured_at="2026-01-01T00:00:00+00:00"),
        ),
    )
    newer = _fact(
        slug="newer",
        title="Newer fact",
        origins=(
            Origin(agent="claude_code", native_path="/y", captured_at="2026-06-01T00:00:00+00:00"),
        ),
    )

    text = render_digest([older, newer], partition="coffer")

    assert text.index("Newer fact") < text.index("Older fact")


def test_no_facts_still_produces_a_usable_digest() -> None:
    """FR-032: the digest step is never a no-op, even with nothing to show."""
    text = render_digest([], partition="global")

    assert "global" in text
    assert text.strip()  # non-empty, non-whitespace


def test_a_fact_with_no_description_still_gets_one_line() -> None:
    text = render_digest([_fact(description="")], partition="coffer")

    assert "- **A fact**" in text


def test_a_blank_title_falls_back_to_the_fact_slug() -> None:
    """A fact whose frontmatter lost its title still renders as a fact.

    Facts are derived from an agent's own memory files, so a blank title is a
    shape the reader can actually hit. Falling back to the slug keeps the line
    identifying *which* fact it is; rendering the emphasis markers around
    nothing would put ``- ****`` in front of the person browsing the folder.
    """
    text = render_digest([_fact(slug="prefers-worktrees", title="  ")], partition="coffer")

    assert "prefers-worktrees" in text
    assert "****" not in text
