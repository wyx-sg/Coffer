from __future__ import annotations

from pathlib import Path

import pytest

from coffer.domain.sync.remote import SyncRemote

from .machines import Machine, bare_remote


@pytest.fixture
def remote(tmp_path: Path) -> SyncRemote:
    return SyncRemote(url=str(bare_remote(tmp_path)))


@pytest.fixture
def mac(tmp_path: Path, remote: SyncRemote) -> Machine:
    return Machine(tmp_path / "mac", "MacBook Pro", remote)


@pytest.fixture
def mini(tmp_path: Path, remote: SyncRemote) -> Machine:
    return Machine(tmp_path / "mini", "Mac mini", remote)


@pytest.fixture
def pair(mac: Machine, mini: Machine) -> tuple[Machine, Machine]:
    """Two machines that have joined the remote and converged."""
    from coffer.application.sync.round_join import join

    mac.put("knowledge/team/on-call.md", "Primary on-call rotates every Monday.\n")
    join(mac.engine, mac.remote, None)
    join(mini.engine, mini.remote, None)
    mac.round()
    mini.round()
    return mac, mini
