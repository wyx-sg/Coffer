"""The vault upgrade completes a pairing that predates owner identification.

A pairing made before pairings recorded the owner's sender id would have the
owner gate refuse its own owner for ever. The runtime refuses an empty sender
id outright, so the one-time upgrade fills it in: the DM — the channel's
earliest pairing — takes its chat id, which on SeaTalk and Telegram is the
user's own id. Group pairings are left as they are.
"""

from __future__ import annotations

import pytest

from coffer.infrastructure.vault.migration.export_vault import owner_sender_filled


@pytest.mark.acceptance(
    spec="channels", scenario="the vault upgrade backfills a DM pairing's sender id"
)
def test_the_dm_pairing_without_a_sender_id_takes_its_chat_id() -> None:
    rows = [
        {"chat_id": "4242", "sender_id": ""},
        {"chat_id": "-100777", "sender_id": ""},
    ]

    filled = owner_sender_filled(rows)

    assert filled == ["4242", ""]
    # A second run changes nothing.
    again = [{**r, "sender_id": s} for r, s in zip(rows, filled, strict=True)]
    assert owner_sender_filled(again) == filled


def test_a_pairing_that_already_names_its_owner_is_kept() -> None:
    rows = [
        {"chat_id": "4242", "sender_id": "emp-7"},
        {"chat_id": "grp", "sender_id": "emp-7"},
    ]

    assert owner_sender_filled(rows) == ["emp-7", "emp-7"]


def test_a_group_chat_id_is_never_taken_for_a_user_id() -> None:
    assert owner_sender_filled([{"chat_id": "-100777", "sender_id": ""}]) == [""]


def test_a_channel_without_pairings_has_nothing_to_fill() -> None:
    assert owner_sender_filled([]) == []
