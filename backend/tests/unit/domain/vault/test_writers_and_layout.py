"""Commit trailers and the vault's areas (coffer.domain.vault.writers / layout)."""

from __future__ import annotations

import pytest

from coffer.domain.vault.content_ids import EMPTY_BLOB, blob_id
from coffer.domain.vault.errors import VaultPathRefused
from coffer.domain.vault.layout import area_of, is_document, resource_path, safe_stem
from coffer.domain.vault.writers import (
    WRITER_AGENT,
    WRITER_DISK,
    CommitMeta,
    display_writer,
    message,
    parse_meta,
)
from coffer.domain.vault.writes import check_path


def test_a_message_carries_every_field_as_a_trailer_and_reads_back() -> None:
    meta = CommitMeta(
        writer=WRITER_AGENT,
        operation="save",
        summary="Saved a note",
        actor="agent:codex",
        agent="codex",
        machine="abc123",
        restored_from="f" * 40,
    )
    text = message(meta)
    assert "Coffer-Writer: agent" in text and "Coffer-Machine: abc123" in text
    assert parse_meta(text) == meta
    assert display_writer(meta) == "agent:codex"


def test_a_hand_made_commit_reads_as_a_disk_edit() -> None:
    meta = parse_meta("fix typo\n\nSigned-off-by: someone\n")
    assert meta.writer == WRITER_DISK and meta.summary == "fix typo"


def test_blob_ids_are_gits() -> None:
    assert blob_id(b"") == EMPTY_BLOB


@pytest.mark.parametrize(
    ("path", "area"),
    [
        ("resources/mcp_server/linear.json", "resources/mcp_server"),
        ("state/channel-peers/bot.json", "state/channel-peers"),
        ("knowledge/global/a.md", "knowledge"),
        ("skills/pdf/SKILL.md", "skills"),
        ("secret/x.enc", "secret"),
        ("manifest.json", "manifest"),
        ("notes.txt", "other"),
    ],
)
def test_every_path_has_one_area(path: str, area: str) -> None:
    assert area_of(path) == area


def test_resources_are_filed_by_name_and_parsed_as_documents() -> None:
    assert resource_path("skill", "pdf-tools") == "resources/skill/pdf-tools.json"
    assert is_document("resources/skill/pdf-tools.json")
    assert not is_document("skills/pdf-tools/SKILL.md")
    assert safe_stem("a/b..c") == "a-b..c"


@pytest.mark.parametrize("bad", ["", "/abs", "a/../b", ".git/config", "a//b", "a\\b"])
def test_only_plain_vault_paths_pass(bad: str) -> None:
    with pytest.raises(VaultPathRefused):
        check_path(bad)
