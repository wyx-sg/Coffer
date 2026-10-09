"""The one-time move of channels out of the vault (ADR
channels-are-machine-local-resources). Delete with ``move_to_local``."""

from __future__ import annotations

import json

from coffer.domain.vault.document import ResourceDocument, encode
from coffer.domain.vault.writers import OP_UPDATE
from coffer.domain.vault.writes import Expect
from coffer.infrastructure.channel.move_to_local import MARKER, SUMMARY, move_channels_to_local
from coffer.infrastructure.vault.actor_meta import commit_meta
from coffer.infrastructure.vault.home import local_root
from coffer.infrastructure.vault.instance import vault_repository, vault_writer

MINE, THEIRS = "a" * 16, "b" * 16
UID = {"here": "1" * 32, "there": "2" * 32, "nowhere": "3" * 32}


def _channel(name: str, runs_on: str | None) -> bytes:
    config: dict[str, object] = {"channel_type": "telegram", "bot_token_ref": f"channel/{name}"}
    if runs_on is not None:
        config["runs_on"] = runs_on
    return ResourceDocument(kind="channel", name=name, uid=UID[name], config=config).to_bytes()


def _peers(name: str, chat: str) -> bytes:
    peer = {"chat_id": chat, "sender_id": "s", "display_name": "", "paired_at": "2026-10-01"}
    return encode({"channel_uid": UID[name], "format_version": 1, "peers": [peer]})


def _seed_vault() -> None:
    with vault_writer().begin(commit_meta(OP_UPDATE, "seed", "system")) as txn:
        txn.write("resources/channel/here.json", _channel("here", MINE), Expect.ABSENT)
        txn.write("resources/channel/there.json", _channel("there", THEIRS), Expect.ABSENT)
        txn.write("resources/channel/nowhere.json", _channel("nowhere", None), Expect.ABSENT)
        txn.write("state/channel-peers/here.json", _peers("here", "dm-1"), Expect.ABSENT)
        txn.write("state/channel-peers/there.json", _peers("there", "dm-2"), Expect.ABSENT)


def _local_channels() -> dict[str, dict[str, object]]:
    folder = local_root() / "resources/channel"
    return {f.stem: json.loads(f.read_text()) for f in folder.glob("*.json")}


def _local_peers() -> dict[str, object]:
    return json.loads((local_root() / "channel-peers.json").read_text())


async def test_this_machine_takes_its_own_and_unbound_channels_and_empties_the_vault() -> None:
    _seed_vault()

    assert move_channels_to_local(MINE) == 2

    local = _local_channels()
    assert sorted(local) == ["here", "nowhere"]
    assert all("runs_on" not in doc["config"] for doc in local.values())  # type: ignore[operator]
    assert local["here"]["uid"] == UID["here"]
    assert list(_local_peers()) == [UID["here"]]
    repo = vault_repository()
    assert repo.tree("HEAD", "resources/channel") == {}
    assert repo.tree("HEAD", "state/channel-peers") == {}
    assert repo.log(limit=1)[0].meta.summary == SUMMARY
    # Once per machine.
    assert move_channels_to_local(MINE) == 0
    assert (local_root() / MARKER).is_file()


async def test_a_machine_migrating_later_reads_its_channel_from_before_the_deletion() -> None:
    _seed_vault()
    move_channels_to_local(MINE)
    # The other machine, after the deletion reached it: same history, its own
    # local/ (nothing moved yet, no marker).
    (local_root() / MARKER).unlink()
    for file in (local_root() / "resources/channel").glob("*.json"):
        file.unlink()
    (local_root() / "channel-peers.json").unlink()

    assert move_channels_to_local(THEIRS) == 2

    assert sorted(_local_channels()) == ["nowhere", "there"]
    assert list(_local_peers()) == [UID["there"]]


async def test_without_a_machine_id_nothing_is_decided() -> None:
    _seed_vault()
    assert move_channels_to_local(None) == 0
    assert not (local_root() / MARKER).exists()
    assert vault_repository().tree("HEAD", "resources/channel") != {}
