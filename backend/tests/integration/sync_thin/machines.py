"""Two (or more) machines, each with its own vault, around one bare remote."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from coffer.application.sync.round_deps import RoundDeps
from coffer.application.sync.round_engine import RoundEngine
from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.rounds import RoundRecord
from coffer.domain.vault.document import ResourceDocument
from coffer.domain.vault.writers import WRITER_USER, CommitMeta
from coffer.domain.vault.writes import Expect, Validator
from coffer.infrastructure.secret.plaintext_scan import find_in_text
from coffer.infrastructure.sync.local_state import ConflictScratch, JsonRemoteStore, JsonRoundState
from coffer.infrastructure.sync.vault_git import VaultSyncGit
from coffer.infrastructure.vault.repository import VaultRepository
from coffer.infrastructure.vault.writer import VaultWriter

USER = CommitMeta(writer=WRITER_USER, operation="save", summary="Saved", actor="user")


class FakeMachine:
    def __init__(self, machine_id: str, label: str) -> None:
        self.id = machine_id
        self.name = label

    def machine_id(self) -> str:
        return self.id

    def label(self) -> str:
        return self.name

    def descriptor_path(self) -> str:
        return f"machines/{self.id}.json"

    def descriptor(self, *, last_round_at: str | None, last_commit: str | None) -> bytes:
        return (
            json.dumps(
                {
                    "machine_id": self.id,
                    "format_version": 1,
                    "name": self.name,
                    "last_converged_commit": last_commit,
                },
                indent=2,
            )
            + "\n"
        ).encode()

    def labels(self, files: Mapping[str, bytes]) -> dict[str, str]:
        out: dict[str, str] = {}
        for data in files.values():
            doc = json.loads(data)
            out[doc["machine_id"]] = doc["name"]
        return out


@dataclass
class Machine:
    root: Path
    label: str
    remote: SyncRemote
    validate: Validator | None = None
    repo: VaultRepository = field(init=False)
    writer: VaultWriter = field(init=False)
    engine: RoundEngine = field(init=False)
    state: JsonRoundState = field(init=False)

    def __post_init__(self) -> None:
        self.repo = VaultRepository(self.root / "vault")
        self.repo.ensure()
        self.state = JsonRoundState(lambda: self.root / "local" / "round.json")
        self.writer = VaultWriter(self.repo, machine=lambda: self.label)
        if self.validate is not None:
            self.writer.set_validator(self.validate)
        self.writer.set_held(lambda: {c.path for c in self.state.join_choices()})
        self.git = VaultSyncGit(self.repo)
        self.deps = RoundDeps(
            git=self.git,
            state=self.state,
            writer=self.writer,
            machine=FakeMachine(self.label, self.label),
            scratch=ConflictScratch(lambda: self.root / "derived" / "sync-conflicts"),
            validate=self.validate,
            find_plaintext=find_in_text,
        )
        self.engine = RoundEngine(self.deps)
        self.remotes = JsonRemoteStore(lambda: self.root / "local" / "remote.json")

    # --- writing like a person or the daemon would ---------------------------

    def put(self, path: str, data: bytes | str) -> None:
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

    def at_head(self, path: str) -> bytes | None:
        return self.repo.read("HEAD", path)

    def round(self) -> RoundRecord:
        return self.engine.run(self.remote, None, trigger="manual")


def bare_remote(tmp: Path) -> Path:
    path = tmp / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(path)], check=True)
    return path


def remote_ref(remote: SyncRemote, branch: str = "main") -> str | None:
    """The branch's tip in the bare remote itself (not any machine's view)."""
    done = subprocess.run(
        ["git", "--git-dir", remote.url, "rev-parse", "--verify", "-q", branch],
        capture_output=True,
        check=False,
    )
    return done.stdout.decode().strip() or None


def resource(kind: str, name: str, uid: str, config: dict[str, object] | None = None) -> bytes:
    return ResourceDocument(kind=kind, name=name, uid=uid, config=config or {}).to_bytes()


def join_all(machines: Sequence[Machine]) -> None:
    """Every machine joins in order, and ends converged."""
    from coffer.application.sync.round_join import join

    for m in machines:
        join(m.engine, m.remote, None)
    for m in machines:
        m.round()
