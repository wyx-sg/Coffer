"""ONE-TIME migration: channels leave the vault for ``local/`` (ADR
channels-are-machine-local-resources).

Channels used to be vault resources that travelled, each naming the one
machine that ran it in ``config.runs_on``, with their pairings in
``state/channel-peers/<channel>.json``. Now a channel is this machine's, like
an agent. On the first start of a build that knows this, each machine:

1. reads the channel files and pairing documents — from ``HEAD``, or, when
   another machine already ran this migration and its deletion has arrived,
   from the commit just before that deletion;
2. moves the channels that are its own (``runs_on`` is this machine, or names
   no machine) to ``local/resources/channel/``, without ``runs_on``, and their
   pairings to ``local/channel-peers.json``;
3. deletes every channel file and pairing document still in the vault in one
   commit, which sync carries to the other machines.

A marker under ``local/`` makes it run once per machine. Delete this module,
its call in ``vault_composition`` and its test once every machine has run it.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from coffer.domain.vault.document import DocumentInvalid, decode, encode
from coffer.domain.vault.layout import RESOURCES, STATE
from coffer.domain.vault.writers import OP_DELETE
from coffer.domain.vault.writes import Expect
from coffer.infrastructure.channel.persistence import peers_path
from coffer.infrastructure.vault.actor_meta import commit_meta
from coffer.infrastructure.vault.atomic import atomic_write
from coffer.infrastructure.vault.home import local_root, vault_root
from coffer.infrastructure.vault.instance import vault_writer
from coffer.infrastructure.vault.json_store import JsonStore
from coffer.infrastructure.vault.repository import VaultRepository

log = logging.getLogger(__name__)

CHANNELS = f"{RESOURCES}/channel"
PEERS = f"{STATE}/channel-peers"
#: The deletion commit's summary — how a machine that migrates later finds it.
SUMMARY = "Moved channels out of the vault: a channel is machine-local"
MARKER = "channels-moved-local.json"


def _documents(repo: VaultRepository, ref: str, prefix: str) -> dict[str, dict[str, Any]]:
    tree = {p: b for p, b in repo.tree(ref, prefix).items() if p.endswith(".json")}
    blobs = repo.read_blobs(sorted(set(tree.values())))
    out: dict[str, dict[str, Any]] = {}
    for path, blob in tree.items():
        try:
            out[path] = decode(blobs.get(blob, b""))
        except DocumentInvalid:
            log.warning("channel.move_local.unreadable", extra={"path": path})
    return out


def _source(repo: VaultRepository) -> str | None:
    """Where the channels are read from: ``HEAD`` while they are still there,
    else the commit before another machine's migration removed them."""
    if repo.tree("HEAD", CHANNELS) or repo.tree("HEAD", PEERS):
        return "HEAD"
    last = repo.log(CHANNELS, limit=1)
    if last and last[0].meta.summary == SUMMARY and last[0].parents:
        return last[0].parents[0]
    return None


def _free(root: Path, path: str, uid: str) -> Path:
    target = root / path
    if not target.exists():
        return target
    return target.with_name(f"{target.stem}-{uid[:8]}{target.suffix}")


def _local_uids(root: Path) -> set[str]:
    uids: set[str] = set()
    for file in (root / CHANNELS).glob("*.json"):
        try:
            uid = json.loads(file.read_bytes()).get("uid")
        except (OSError, ValueError):
            continue
        if isinstance(uid, str):
            uids.add(uid)
    return uids


def move_channels_to_local(machine_id: str | None, home: Path | None = None) -> int:
    """Run the migration on this machine (blocking); the number of channels
    moved to ``local/``. A no-op once the marker exists; without a machine id
    nothing is decided and it runs again next start."""
    marker = local_root(home) / MARKER
    if marker.exists():
        return 0
    if not machine_id:
        log.warning("channel.move_local.no_machine_id")
        return 0
    writer = vault_writer(vault_root(home))
    repo = writer.repo
    repo.ensure()
    source = _source(repo)
    moved = 0
    if source is not None:
        root = local_root(home)
        present = _local_uids(root)
        peers = {
            doc["channel_uid"]: doc.get("peers")
            for doc in _documents(repo, source, PEERS).values()
            if isinstance(doc.get("channel_uid"), str)
        }
        pairings: dict[str, Any] = {}
        for path, doc in sorted(_documents(repo, source, CHANNELS).items()):
            uid = doc.get("uid")
            config = doc.get("config")
            if not isinstance(uid, str) or not isinstance(config, dict):
                continue
            runs_on = config.pop("runs_on", None)
            if runs_on and runs_on != machine_id:
                continue  # another machine's channel: that machine moves it
            if uid in present:
                continue
            atomic_write(_free(root, path, uid), encode(doc))
            if isinstance(peers.get(uid), list) and peers[uid]:
                pairings[uid] = {"peers": peers[uid]}
            moved += 1
        if pairings:
            JsonStore(peers_path(home)).update(lambda current: {**current, **pairings})
    stale = sorted({*repo.tree("HEAD", CHANNELS), *repo.tree("HEAD", PEERS)})
    if stale:
        with writer.begin(commit_meta(OP_DELETE, SUMMARY, "system")) as txn:
            for path in stale:
                txn.delete(path, Expect.HEAD)
    atomic_write(marker, (json.dumps({"at": datetime.now(UTC).isoformat()}) + "\n").encode())
    if moved or stale:
        log.info("channel.move_local.done moved=%d removed=%d", moved, len(stale))
    return moved


__all__ = ["MARKER", "SUMMARY", "move_channels_to_local"]
