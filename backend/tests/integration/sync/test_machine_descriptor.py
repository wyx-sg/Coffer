"""What one machine's descriptor says about it (spec vault-sync).

The descriptor at ``machines/<machine_id>.yaml`` is the only document a machine
writes about itself, and the registry every machine renders is read out of it.
These tests read it the way another machine does — out of the remote's branch,
through git — after real rounds against a real bare repository, because what
matters is what crossed, not what the registry object believes it wrote.
"""

from __future__ import annotations

import pathlib
import socket
import subprocess
from datetime import date

import pytest
import yaml

from tests.integration.sync.harness import MACHINE_A, VaultMachine, two_machines

pytestmark = pytest.mark.timeout(120)

_DESCRIPTOR = f"machines/{MACHINE_A}.yaml"


@pytest.fixture
async def pair(tmp_path: pathlib.Path):
    a, b = await two_machines(tmp_path)
    yield a, b
    await a.close()
    await b.close()


async def _published(machine: VaultMachine) -> dict:
    raw = await machine.remote_text(_DESCRIPTOR)
    assert raw is not None, "the descriptor never reached the remote"
    doc = yaml.safe_load(raw)
    assert isinstance(doc, dict)
    return doc


def _in_remote_history(machine: VaultMachine, commit: str) -> bool:
    done = subprocess.run(
        ["git", "-C", machine.remote_url, "cat-file", "-e", f"{commit}^{{commit}}"],
        check=False,
        capture_output=True,
    )
    return done.returncode == 0


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a descriptor carries what the machines table shows"
)
async def test_the_published_descriptor_carries_every_fact_the_table_shows(pair) -> None:
    a, _b = pair
    await a.register("agent", "claude-code", {"value": "cc"})
    await a.register("agent", "codex", {"value": "codex"})
    # The first round (the explicit join) has no pointer to publish yet; the
    # second fills it in.
    await a.adopt()
    await a.converge()

    doc = await _published(a)

    assert doc["name"] == "laptop"
    assert isinstance(doc["os"], str) and doc["os"]
    assert doc["hostname"] == socket.gethostname()
    assert doc["coffer_version"] == "test"
    # The day it last converged (published as ``last_converged_on``) and the
    # commit it reached.
    assert doc["last_converged_on"] == date.today().isoformat()
    assert isinstance(doc["last_converged_commit"], str) and doc["last_converged_commit"]
    # The same short hash this machine reports for its own key, and never the key.
    assert doc["key_fingerprint"] == a.key_fingerprint()
    assert doc["key_fingerprint"] not in a.master_key.export_key().decode("latin-1")
    assert doc["agents"] == ["claude-code", "codex"]


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a descriptor publishes the pointer this machine reached"
)
async def test_the_descriptor_names_the_pointer_this_machine_held(pair) -> None:
    a, _b = pair
    a.write_knowledge("notes", "first", "hello\n")
    first = await a.adopt()
    pointer = await a.state.pointer()
    assert pointer == first.commit

    # The next round serializes with that pointer in hand and publishes it.
    await a.converge()

    doc = await _published(a)
    assert doc["last_converged_commit"] == pointer
    # It is a base another machine can actually be handed back: the remote holds it.
    assert _in_remote_history(a, pointer)


@pytest.mark.acceptance(
    spec="vault-sync", scenario="an idle machine restamps its descriptor at most once a day"
)
async def test_later_rounds_the_same_day_leave_the_descriptor_alone(pair) -> None:
    a, _b = pair
    a.write_knowledge("notes", "first", "hello\n")
    await a.adopt()
    await a.converge()  # fills in the commit the first round could not name
    stamped = await a.remote_text(_DESCRIPTOR)
    remote_commits = await a.remote_commit_count()
    local_commits = await a.local_commit_count()

    # Idle rounds: no heartbeat commit, no rewritten descriptor.
    for _ in range(3):
        run = await a.converge()
        assert run.commit is None or run.commit == await a.state.pointer()
    assert await a.remote_commit_count() == remote_commits
    assert await a.local_commit_count() == local_commits
    assert await a.remote_text(_DESCRIPTOR) == stamped

    # A round that does change something, still the same day, moves the
    # pointer but not the day's stamp.
    a.write_knowledge("notes", "second", "again\n")
    await a.converge()
    assert await a.remote_commit_count() == remote_commits + 1
    assert await a.remote_text(_DESCRIPTOR) == stamped
    assert yaml.safe_load(stamped)["last_converged_on"] == date.today().isoformat()
