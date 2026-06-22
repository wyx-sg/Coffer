"""Unit: deterministic project ULID + per-fact markdown render/parse.

Pure string/ID logic — no filesystem, no banned I/O imports.
"""

from __future__ import annotations

from dataclasses import fields
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
        "title": "deploy-fact",
        "description": "deploys via make release",
        "body": "This repo deploys via make release.",
        "actor": "agent",
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


def test_memory_fact_has_no_free_form_type_field() -> None:
    # Lane is the single classification axis (FR-048); the free-form `type`
    # field is retired from the domain model.
    assert "type" not in {f.name for f in fields(MemoryFact)}


def test_render_fact_markdown_has_frontmatter() -> None:
    text = render_fact_markdown(_fact())
    assert text.startswith("---\n")
    assert "kind: knowledge" in text
    assert "title: deploy-fact" in text
    assert "actor: agent" in text
    # No free-form `type` axis — Lane is the only classification (FR-048).
    assert "type:" not in text
    assert "origin_session_id: sess-1" in text
    assert "This repo deploys via make release." in text


def test_render_then_parse_roundtrips() -> None:
    fact = _fact()
    text = render_fact_markdown(fact)
    parsed = parse_fact_markdown(text, fallback_id="x", mtime=datetime(2026, 6, 9, tzinfo=UTC))
    assert parsed.id == fact.id
    assert parsed.title == fact.title
    assert parsed.description == fact.description
    assert parsed.actor == "agent"
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
    assert parsed.title == "abc"
    assert "preferences" in parsed.description
    assert "preferences" in parsed.body


def test_parse_tolerates_malformed_frontmatter() -> None:
    # An agent-written file whose frontmatter value has an unquoted colon —
    # invalid YAML. It must degrade (filename id, first-body-line description),
    # never raise, so one bad file cannot 500 the whole /facts listing.
    text = (
        "---\n"
        "title: Engineering conventions\n"
        "description: catalogued in `agents/` (10 topic files: storage, testing)\n"
        "type: feedback\n"
        "---\n"
        "The repo holds a living set of operating manuals.\n"
    )
    parsed = parse_fact_markdown(
        text, fallback_id="feedback_x", mtime=datetime(2026, 6, 9, tzinfo=UTC)
    )
    assert parsed.id == "feedback_x"
    assert parsed.title == "feedback_x"  # frontmatter unparseable → filename fallback
    assert "operating manuals" in parsed.description
    assert "operating manuals" in parsed.body


def test_parse_accepts_legacy_name_key_as_title() -> None:
    # Existing stores / externally-written files predate the name→title rename.
    # The legacy ``name:`` frontmatter key must still parse as the title.
    text = "---\nid: 01ABCDEF\nname: legacy-titled-fact\ndescription: d\n---\nbody line\n"
    parsed = parse_fact_markdown(text, fallback_id="x", mtime=datetime(2026, 6, 9, tzinfo=UTC))
    assert parsed.title == "legacy-titled-fact"


def test_render_omits_optional_fields_when_absent() -> None:
    fact = _fact(origin_session_id=None)
    text = render_fact_markdown(fact)
    # Lane is the only taxonomy — `type` is never rendered (FR-048).
    assert "type:" not in text
    assert "origin_session_id:" not in text


def test_fact_timestamps_persist_in_frontmatter(tmp_path) -> None:
    """created_at/updated_at must live in the frontmatter (the source of
    truth) — falling back to file mtime silently rewrites history on every
    copy/restore/out-of-band touch (review M6)."""
    from datetime import UTC, datetime

    from coffer.domain.memory.fact import MemoryFact
    from coffer.infrastructure.memory.files import read_fact_file, write_fact_file

    created = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    updated = datetime(2026, 5, 6, 7, 8, 9, tzinfo=UTC)
    fact = MemoryFact(
        id="01HZX5XKQW9YV3T8R2M4N6PABC",
        title="ts",
        description="d",
        body="body",
        actor="user",
        origin_session_id=None,
        created_at=created,
        updated_at=updated,
    )
    path = tmp_path / "ts-01HZX5XKQW9YV3T8R2M4N6PABC.md"
    write_fact_file(path, fact)

    parsed = read_fact_file(path).fact
    assert parsed.created_at == created
    assert parsed.updated_at == updated
