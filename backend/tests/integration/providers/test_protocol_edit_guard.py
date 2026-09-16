"""Correcting a mis-probed wire is allowed; doing it under a live agent is not.

``protocol`` is mutable on purpose — the probe that guessed the wire can be
wrong, and the fix must not cost the user their key. But the wire is not inert
the way the docstrings once claimed. Two things read it:

- ``targets.scoped_targets`` returns nothing for ``ollama`` BEFORE scope is
  consulted, so a keyless connection covers no agent at all; and
- ``service._AGENT_FOR_WIRE`` is how ``use-builtin <wire>`` finds the agent to
  put back on its own login.

So patching the wire of a connection that is currently projected would strand
that projection: the native config Coffer already wrote stays behind while
nothing would ever reach it to take it off again. The guard refuses the edit
instead — the user asked to change a field, not to take their agents off a
gateway.

Real ``create_app()`` over a real SQLite file and a real agent config dir, so
the assertion "the file on disk did not move" is about the actual file.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

TOKEN = "test-token-provider-wire-guard"


def _app(tmp_path: pathlib.Path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    return create_app()


def _client(app) -> TestClient:
    set_active_token(TOKEN)
    return TestClient(app, headers={"X-Coffer-Token": TOKEN})


def _anthropic_body(name: str = "acme", **over) -> dict:
    body = {
        "name": name,
        "protocol": "anthropic",
        "base_url": "https://gw/anthropic",
        "secret_value": "sk-secret-value",
    }
    body.update(over)
    return body


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="correcting a mis-probed wire is refused while the connection is live",
)
def test_patch_refuses_to_move_the_wire_of_a_live_connection(tmp_path, monkeypatch):
    """An active connection's wire is pinned while it is projected.

    The refusal is a 409 the user can act on: it names the connection and the
    command that puts the agents back first. The native config it already wrote
    must be byte-for-byte what it was before the refused patch.
    """
    app = _app(tmp_path, monkeypatch, 59810)
    cfg = tmp_path / "agent-cfg"
    cfg.mkdir(parents=True, exist_ok=True)
    with _client(app) as c:
        r = c.post(
            "/api/v1/agents",
            json={"type": "claude_code", "name": "cc", "config_dir": str(cfg)},
        )
        assert r.status_code == 201, r.text
        c.post("/api/v1/providers", json=_anthropic_body())
        assert c.post("/api/v1/providers/acme/activate").status_code == 200
        projected = (cfg / "settings.json").read_text()
        assert json.loads(projected)["env"]["ANTHROPIC_BASE_URL"] == "https://gw/anthropic"

        bad = c.patch("/api/v1/providers/acme", json={"protocol": "openai"})
        assert bad.status_code == 409, bad.text
        envelope = bad.json()["error"]
        assert envelope["code"] == "PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE"
        assert "acme" in envelope["message"]
        assert "use-builtin" in envelope["message"]

        # Nothing moved: not the stored wire, not the file the agent reads.
        assert c.get("/api/v1/providers/acme").json()["protocol"] == "anthropic"
        assert (cfg / "settings.json").read_text() == projected


def test_patch_still_edits_other_fields_of_a_live_connection(tmp_path, monkeypatch):
    """The guard is about the wire only — a live connection's endpoint still
    moves, or correcting a typo'd base URL would need a de-projection too."""
    app = _app(tmp_path, monkeypatch, 59820)
    with _client(app) as c:
        c.post("/api/v1/providers", json=_anthropic_body())
        assert c.post("/api/v1/providers/acme/activate").status_code == 200
        r = c.patch("/api/v1/providers/acme", json={"base_url": "https://gw/anthropic/v2"})
        assert r.status_code == 200, r.text
        assert r.json()["base_url"] == "https://gw/anthropic/v2"


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="correcting a mis-probed wire is refused while the connection is live",
)
def test_patch_accepts_the_current_wire_resent_on_a_live_connection(tmp_path, monkeypatch):
    """Re-sending the wire the connection already has is not a change.

    A client that submits the whole form rather than a diff must not be told
    its unchanged dropdown is a conflict.
    """
    app = _app(tmp_path, monkeypatch, 59830)
    with _client(app) as c:
        c.post("/api/v1/providers", json=_anthropic_body())
        assert c.post("/api/v1/providers/acme/activate").status_code == 200
        r = c.patch(
            "/api/v1/providers/acme",
            json={"protocol": "anthropic", "base_url": "https://gw/anthropic/v3"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["protocol"] == "anthropic"
        assert r.json()["base_url"] == "https://gw/anthropic/v3"


def test_patch_moves_the_wire_of_a_connection_that_is_not_live(tmp_path, monkeypatch):
    """The whole reason the field is mutable: a mis-probed wire corrected in
    place, key and all, on a connection that projects into nothing."""
    app = _app(tmp_path, monkeypatch, 59840)
    with _client(app) as c:
        c.post("/api/v1/providers", json=_anthropic_body())
        ref = c.get("/api/v1/providers/acme").json()["credential_ref"]
        r = c.patch("/api/v1/providers/acme", json={"protocol": "openai"})
        assert r.status_code == 200, r.text
        assert r.json()["protocol"] == "openai"
        # The key stayed exactly where it was — that is what "in place" buys.
        assert r.json()["credential_ref"] == ref
        assert c.get(f"/api/v1/credentials/{ref}/exists").json()["present"] is True


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="correcting a mis-probed wire is refused while the connection is live",
)
def test_the_wire_moves_again_once_the_agents_are_back_on_their_own_login(tmp_path, monkeypatch):
    """The refusal names a way out, and the way out works.

    ``use-builtin`` de-projects and clears ``is_active``; the same patch that
    was refused a moment ago then succeeds.
    """
    app = _app(tmp_path, monkeypatch, 59850)
    cfg = tmp_path / "agent-cfg"
    cfg.mkdir(parents=True, exist_ok=True)
    with _client(app) as c:
        c.post(
            "/api/v1/agents",
            json={"type": "claude_code", "name": "cc", "config_dir": str(cfg)},
        )
        c.post("/api/v1/providers", json=_anthropic_body())
        c.post("/api/v1/providers/acme/activate")
        assert c.patch("/api/v1/providers/acme", json={"protocol": "openai"}).status_code == 409

        assert c.post("/api/v1/providers/use-builtin/anthropic").status_code == 200
        ok = c.patch("/api/v1/providers/acme", json={"protocol": "openai"})
        assert ok.status_code == 200, ok.text
        assert ok.json()["protocol"] == "openai"
        # And the config it had written is gone, so nothing was stranded.
        settings = json.loads((cfg / "settings.json").read_text())
        assert "ANTHROPIC_BASE_URL" not in settings.get("env", {})


@pytest.mark.parametrize("wire", ["ollama", "unknown"])
def test_the_guard_covers_every_wire_not_just_the_two_that_reach_an_agent(
    tmp_path, monkeypatch, wire
):
    """``ollama`` is the sharpest case — it covers no agent at all, so moving a
    live connection onto it empties its targets while the file stays — but the
    rule is the same for every value, including ``unknown``."""
    app = _app(tmp_path, monkeypatch, 59860 + 10 * ["ollama", "unknown"].index(wire))
    with _client(app) as c:
        c.post("/api/v1/providers", json=_anthropic_body())
        assert c.post("/api/v1/providers/acme/activate").status_code == 200
        bad = c.patch("/api/v1/providers/acme", json={"protocol": wire})
        assert bad.status_code == 409, bad.text
        assert bad.json()["error"]["code"] == "PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE"
