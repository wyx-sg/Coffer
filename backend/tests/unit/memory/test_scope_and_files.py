"""Unit: deterministic project ULID + per-fact markdown render/parse.

Pure string/ID logic — no filesystem, no banned I/O imports.
"""

from __future__ import annotations

from datetime import UTC, datetime

from coffer.domain.memory.fact import MemoryFact
from coffer.infrastructure.memory.files import (
    parse_fact_markdown,
    render_fact_markdown,
)
from coffer.infrastructure.memory.scope_fs import project_ulid


def _fact(**kw) -> MemoryFact:
    now = datetime(2026, 6, 9, tzinfo=UTC)
    base: dict = {
        "id": "01ABCDEF",
        "name": "deploy-fact",
        "description": "deploys via make release",
        "body": "This repo deploys via make release.",
        "actor": "agent",
        "type": "project",
        "origin_session_id": "sess-1",
        "created_at": now,
        "updated_at": now,
    }
    base.update(kw)
    return MemoryFact(**base)


def test_project_ulid_is_deterministic_and_26_chars() -> None:
    a = project_ulid("/Users/dev/repo")
    b = project_ulid("/Users/dev/repo")
    c = project_ulid("/Users/dev/other")
    assert a == b
    assert a != c
    assert len(a) == 26
    # Crockford base32 alphabet only.
    assert set(a) <= set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")


def test_render_fact_markdown_has_frontmatter() -> None:
    text = render_fact_markdown(_fact())
    assert text.startswith("---\n")
    assert "name: deploy-fact" in text
    assert "actor: agent" in text
    assert "type: project" in text
    assert "origin_session_id: sess-1" in text
    assert "This repo deploys via make release." in text


def test_render_then_parse_roundtrips() -> None:
    fact = _fact()
    text = render_fact_markdown(fact)
    parsed = parse_fact_markdown(text, fallback_id="x", mtime=datetime(2026, 6, 9, tzinfo=UTC))
    assert parsed.id == fact.id
    assert parsed.name == fact.name
    assert parsed.description == fact.description
    assert parsed.actor == "agent"
    assert parsed.type == "project"
    assert parsed.origin_session_id == "sess-1"
    assert parsed.body == fact.body


def test_parse_degrades_gracefully_for_out_of_band_file() -> None:
    # A hand-written fact file with no frontmatter (e.g. Claude's own).
    parsed = parse_fact_markdown(
        "Just a plain memory line about preferences.",
        fallback_id="abc",
        mtime=datetime(2026, 6, 9, tzinfo=UTC),
    )
    assert parsed.id == "abc"
    assert parsed.actor == "user"  # default actor when absent
    assert parsed.name == "abc"
    assert "preferences" in parsed.description
    assert "preferences" in parsed.body


def test_render_omits_optional_fields_when_absent() -> None:
    fact = _fact(type=None, origin_session_id=None)
    text = render_fact_markdown(fact)
    assert "type:" not in text
    assert "origin_session_id:" not in text
