"""Machines with the whole sync service, around one bare remote.

Each :class:`Box` is one machine: its own vault repository and writer, its
round state and remote file, and a :class:`SyncService` over the real round
engine — only the history (in memory), the audit trail, the master key and
the push token are stand-ins. Everything lives under the test's ``tmp_path``.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from coffer.application.secret.plaintext_ignore import fingerprinter
from coffer.application.sync.round_deps import RoundDeps
from coffer.application.sync.round_engine import RoundEngine
from coffer.application.sync.service import SyncService
from coffer.domain.sync.errors import MasterKeyFileInvalid, MasterKeyPassphraseWrong
from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.rounds import RoundRecord
from coffer.domain.vault.findings import Finding, FindingCode
from coffer.domain.vault.writers import WRITER_USER, CommitMeta
from coffer.domain.vault.writes import Change, Expect, TreeReader, Verdict
from coffer.infrastructure.secret.plaintext_ignore_store import JsonPlaintextIgnores
from coffer.infrastructure.secret.plaintext_mask import find_text, mask_text
from coffer.infrastructure.sync.local_state import ConflictScratch, JsonRemoteStore, JsonRoundState
from coffer.infrastructure.sync.machine_descriptor import HostMachine
from coffer.infrastructure.sync.vault_git import VaultSyncGit
from coffer.infrastructure.vault.repository import VaultRepository
from coffer.infrastructure.vault.writer import VaultWriter
from tests.integration.sync_thin.machines import bare_remote

USER = CommitMeta(writer=WRITER_USER, operation="save", summary="Saved", actor="user")


def json_documents(changes: Sequence[Change], _history: TreeReader) -> Verdict:
    """Refuse a ``resources/`` file that is not a JSON object — enough of the
    real validator for a hand edit to be invalid."""
    findings: list[Finding] = []
    for c in changes:
        if not c.path.startswith("resources/") or c.data is None:
            continue
        try:
            ok = isinstance(json.loads(c.data), dict)
        except ValueError:
            ok = False
        if not ok:
            findings.append(Finding(c.path, FindingCode.INVALID_DOCUMENT, "not a JSON object"))
    return Verdict(findings=findings)


class MemoryHistory:
    def __init__(self) -> None:
        self.rows: list[RoundRecord] = []

    async def append(self, record: RoundRecord) -> RoundRecord:
        stored = RoundRecord.from_json(record.to_json(), id=len(self.rows) + 1)
        self.rows.append(stored)
        return stored

    async def recent(
        self, limit: int, after: tuple[datetime, int] | None = None
    ) -> list[RoundRecord]:
        def key(r: RoundRecord) -> tuple[datetime, int]:
            return datetime.fromisoformat(r.finished_at), r.id or 0

        ordered = sorted(self.rows, key=key, reverse=True)
        if after is not None:
            ordered = [r for r in ordered if key(r) < after]
        return ordered[:limit]

    async def get(self, round_id: int) -> RoundRecord | None:
        return next((r for r in self.rows if r.id == round_id), None)

    async def count(self) -> int:
        return len(self.rows)


class RecordingAudit:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def record(self, event_type: str, **kwargs: Any) -> None:
        self.events.append((event_type, kwargs))


class FakeKey:
    def __init__(self, fingerprint: str | None = "abc123abc123") -> None:
        self.value = fingerprint
        self.installed: bytes | None = None

    def export_key(self) -> bytes | None:
        return b"key" if self.value else None

    def install_key(self, key: bytes) -> None:
        if not key.startswith(b"ok"):
            raise ValueError("not a key")
        self.installed = key

    def fingerprint(self) -> str | None:
        return self.value

    def peek_backup(self, material: str) -> tuple[str, bool]:
        return "f11e" * 3, material.startswith("{")

    def open_backup(self, material: str, passphrase: str | None) -> bytes:
        raw = material.strip().encode("utf-8")
        if not raw:
            raise MasterKeyFileInvalid("<import>", "no key material supplied")
        if material.startswith("{") and passphrase != "right passphrase":
            raise MasterKeyPassphraseWrong()
        return raw


class FakeSecrets:
    def __init__(self) -> None:
        self.locked: list[str] = []
        self.files = 0

    def count(self) -> int:
        return self.files

    def locked_refs(self) -> list[str]:
        return list(self.locked)


class FixedToken:
    """The push token port: ``None`` unless a test makes it raise."""

    def __init__(self) -> None:
        self.error: Exception | None = None

    async def bind(self, remote: SyncRemote, *, actor: str) -> None:
        return None

    async def token_for(self, remote: SyncRemote) -> str | None:
        if self.error is not None:
            raise self.error
        return None


@dataclass
class Box:
    root: Path
    machine_id: str
    label: str
    url: str
    validate: bool = False
    cloud: Callable[[], str | None] = lambda: None
    names: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.names["name"] = self.label
        self.repo = VaultRepository(self.root / "vault")
        self.repo.ensure()
        self.writer = VaultWriter(self.repo, machine=lambda: self.machine_id)
        if self.validate:
            self.writer.set_validator(json_documents)
        self.state = JsonRoundState(lambda: self.root / "local" / "sync" / "round.json")
        self.writer.set_held(lambda: {c.path for c in self.state.join_choices()})
        self.remotes = JsonRemoteStore(lambda: self.root / "local" / "sync" / "remote.json")
        self.git = VaultSyncGit(self.repo)
        self.host = HostMachine(
            machine_id=self.machine_id,
            name=lambda: self.names["name"],
            os_label=lambda: "Darwin 24.6.0",
            coffer_version="0.9.0",
            key_fingerprint=lambda: "abc123abc123",
            hostname=lambda: f"{self.machine_id}.local",
        )
        self.deps = RoundDeps(
            git=self.git,
            state=self.state,
            writer=self.writer,
            machine=self.host,
            scratch=ConflictScratch(lambda: self.root / "derived" / "sync-conflicts"),
            validate=json_documents if self.validate else None,
            cloud_folder=self.cloud,
            find_plaintext=lambda text, path: find_text(
                text, path, fingerprinter(lambda: bytes(range(32)))
            ),
            ignores=JsonPlaintextIgnores(
                lambda: self.root / "local" / "sync" / "plaintext-ignored.json"
            ),
            mask_plaintext=mask_text,
        )
        self.engine = RoundEngine(self.deps)
        self.history = MemoryHistory()
        self.audit = RecordingAudit()
        self.key = FakeKey()
        self.secrets = FakeSecrets()
        self.token = FixedToken()
        self.service = SyncService(
            engine=self.engine,
            remotes=self.remotes,
            history=self.history,
            token=self.token,
            machine=self.host,
            master_key=self.key,
            secrets=self.secrets,
            probe=self.git,
            audit=self.audit,  # type: ignore[arg-type]
            set_machine_name=lambda n: self.names.__setitem__("name", n),
            vault_path=lambda: self.repo.root,
        )
        self.remotes.put(SyncRemote(url=self.url))

    # --- writing like a person --------------------------------------------------

    def put(self, path: str, data: str | bytes) -> None:
        body = data.encode() if isinstance(data, str) else data
        current = self.writer.read_disk(path)
        self.writer.write_file(
            path, body, meta=USER, expected=Expect.ABSENT if current is None else Expect.HEAD
        )

    def remove(self, *paths: str) -> None:
        with self.writer.begin(USER) as txn:
            for path in paths:
                txn.delete(path, Expect.HEAD)

    def disk(self, path: str) -> bytes | None:
        return self.writer.read_disk(path)

    def run(self, coro: Any) -> Any:
        return asyncio.run(coro)

    def round(self) -> RoundRecord:
        record: RoundRecord = asyncio.run(self.service.run())
        return record


def fleet(tmp: Path, *labels: str, validate: bool = False) -> list[Box]:
    """Machines around one fresh bare remote, each joined in order."""
    url = str(bare_remote(tmp))
    boxes = [
        Box(
            tmp / label.lower().replace(" ", "-"),
            label.lower().replace(" ", "-"),
            label,
            url,
            validate,
        )
        for label in labels
    ]
    return boxes


def joined(tmp: Path, *labels: str, validate: bool = False) -> list[Box]:
    boxes = fleet(tmp, *labels, validate=validate)
    boxes[0].put("knowledge/team/on-call.md", "Primary on-call rotates every Monday.\n")
    for box in boxes:
        box.run(box.service.join())
    for box in boxes:
        box.round()
    return boxes


__all__ = ["Box", "fleet", "joined", "json_documents"]
