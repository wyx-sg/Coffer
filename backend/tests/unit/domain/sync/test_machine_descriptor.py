"""A machine's descriptor, ``machines/<id>.json`` (spec vault-sync "Carry the
descriptor fields", "Record plugins as an inventory, not a replicator")."""

from __future__ import annotations

import pytest

import json

from coffer.domain.sync.machine import (
    AgentInventory,
    MachineDescriptor,
    Plugin,
    derive_machine_id,
    descriptor_path,
    machine_id_of,
)


@pytest.mark.acceptance(spec="vault-sync", scenario="a descriptor carries what the machines table shows")
def test_a_descriptor_round_trips_through_its_file() -> None:
    d = MachineDescriptor(
        machine_id="a1b2c3d4e5f60718",
        name="MacBook Pro",
        os="Darwin 24.6.0",
        hostname="mbp.local",
        coffer_version="0.9.0",
        last_round_at="2026-09-30T08:00:00+00:00",
        last_converged_commit="abc",
        key_fingerprint="0123456789ab",
        agents=(
            AgentInventory("codex", "codex", (Plugin("linear", "Linear", "openai", True, "1.2"),)),
        ),
    )
    data = d.to_bytes()
    assert data.endswith(b"\n")
    assert json.loads(data)["format_version"] == 1
    assert MachineDescriptor.parse(d.machine_id, data) == d


def test_a_descriptor_from_a_newer_build_still_reads() -> None:
    raw = json.dumps(
        {
            "format_version": 7,
            "name": "Mini",
            "agents": [{"type": "claude_code", "x": 1}, {}],
            "new": 1,
        }
    ).encode()
    d = MachineDescriptor.parse("m1", raw)
    assert d is not None
    assert (d.machine_id, d.name, d.last_round_at) == ("m1", "Mini", None)
    assert [a.type for a in d.agents] == ["claude_code"]
    assert MachineDescriptor.parse("m1", b"not json") is None


@pytest.mark.acceptance(spec="vault-sync", scenario="the raw host identifier never reaches the repository")
def test_the_id_is_a_digest_and_names_one_path() -> None:
    mid = derive_machine_id("IOPlatformUUID-1234")
    assert len(mid) == 16 and "1234" not in mid
    assert machine_id_of(descriptor_path(mid)) == mid
    assert machine_id_of("machines/nested/x.json") is None
    assert machine_id_of("knowledge/x.json") is None
