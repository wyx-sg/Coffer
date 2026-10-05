"""The local-process grant: `coffer run` hands a standalone secret to a program
only after a person granted it in the desktop app (spec secret "Resolve
standalone secrets into one child with coffer run").

The threat these tests stand for: an agent that can run `coffer run --secret
X -- <its own script>` owns the child, so masking its output hides nothing from
it. The value must therefore not be handed out at all until a person said so —
whatever the approval switch, whatever the build. Every value here is made up.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import sys
from collections.abc import Iterator

import pytest
from typer.testing import CliRunner

from coffer.surfaces.cli.main import app as cli_app
from tests.support.boundary_daemon import (
    BoundaryDaemon,
    point_cli_at,
    prepare_home,
    running_daemon,
)

_runner = CliRunner()
FAKE = "fake-postman-key-0123456789"
NAME = "postman-key"


def _daemon(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, *, approvals: bool
) -> Iterator[BoundaryDaemon]:
    db = prepare_home(tmp_path, monkeypatch, approvals=approvals)
    with running_daemon(tmp_path, db) as d:
        point_cli_at(d, monkeypatch)
        d.store(f"secret/{NAME}", FAKE)
        yield d


@pytest.fixture
def d(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BoundaryDaemon]:
    yield from _daemon(tmp_path, monkeypatch, approvals=True)


@pytest.fixture
def unsigned(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BoundaryDaemon]:
    """An unsigned build's default: the approval switch is off."""
    yield from _daemon(tmp_path, monkeypatch, approvals=False)


def _resolve(d: BoundaryDaemon, *names: str) -> object:
    return d.client.post(
        "/api/v1/secrets/resolve", json={"names": list(names), "argv0": "sh", "cwd": "/tmp"}
    )


def _dumps(d: BoundaryDaemon) -> str:
    """Everything the daemon would show anyone: audit, approvals, the listing,
    and its machine-local boundary files."""
    parts = [
        json.dumps(d.audit_all()),
        d.client.get("/api/v1/secrets/approvals").text,
        d.client.get("/api/v1/secrets").text,
        *(json.dumps(d.local_secrets(n)) for n in ("bindings", "approvals", "settings")),
    ]
    return "\n".join(parts)


# --- refused until a person grants it -------------------------------------------------


@pytest.mark.acceptance(
    spec="secret", scenario="coffer run gets nothing until a person grants the secret"
)
def test_resolve_without_a_grant_is_refused_and_reads_nothing(d: BoundaryDaemon) -> None:
    r = _resolve(d, NAME)

    assert r.status_code == 409
    body = r.json()["error"]
    assert body["code"] == "SECRET_BINDING_PENDING"
    assert FAKE not in r.text
    assert d.audit("secret_resolved") == []
    [waiting] = d.pending()
    assert waiting["destination_kind"] == "local_process"
    assert waiting["ref"] == f"secret/{NAME}"
    assert "agent" in waiting["description"]
    assert FAKE not in _dumps(d)


def test_the_approval_switch_off_does_not_grant_it(unsigned: BoundaryDaemon) -> None:
    """An unsigned build approves new destinations by default; local programs
    still need a person."""
    d = unsigned
    assert d.client.get("/api/v1/settings/secret-boundary").json()["require_approval"] is False

    r = _resolve(d, NAME)

    assert r.status_code == 409 and FAKE not in r.text
    assert d.audit("secret_resolved") == []


def test_a_caller_cannot_approve_its_own_request(d: BoundaryDaemon) -> None:
    _resolve(d, NAME)
    [waiting] = d.pending()
    url = f"/api/v1/secrets/approvals/{waiting['id']}/approve"

    unsigned_call = d.client.post(url, json={})
    forged = d.client.post(url, json={"nonce": "n" * 32, "signature": "0" * 64})
    other_op = d.grant("reveal", f"secret/{NAME}")
    wrong_grant = d.client.post(url, json=other_op)

    for r in (unsigned_call, forged, wrong_grant):
        assert r.status_code in (400, 401, 403, 422), r.text
        assert FAKE not in r.text
    assert _resolve(d, NAME).status_code == 409


def test_a_grant_is_never_one_of_a_batch(d: BoundaryDaemon) -> None:
    """Handing a value to programs an agent can start takes its own prompt; a
    batch approval skips it."""
    from coffer.domain.secrets import batch_target

    _resolve(d, NAME)
    [waiting] = d.pending()
    items = [{"id": waiting["id"], "fingerprint": waiting["target_fingerprint"]}]
    target = batch_target((i["id"], i["fingerprint"]) for i in items)

    r = d.client.post(
        "/api/v1/secrets/approvals/approve",
        json={"items": items, **d.grant("approve_batch", target)},
    )

    assert r.status_code == 200, r.text
    [result] = r.json()["results"]
    assert result["outcome"] == "skipped" and result["reason"] == "not_batchable"
    assert _resolve(d, NAME).status_code == 409


def test_a_refused_grant_stays_refused(d: BoundaryDaemon) -> None:
    _resolve(d, NAME)
    [waiting] = d.pending()
    assert d.client.post(f"/api/v1/secrets/approvals/{waiting['id']}/reject").status_code == 200

    again = _resolve(d, NAME)

    assert again.status_code == 409
    assert again.json()["error"]["code"] == "SECRET_BINDING_REJECTED"
    assert d.pending() == []


@pytest.mark.acceptance(
    spec="secret", scenario="asking for the grant again after a refusal puts a new request up"
)
def test_asking_again_after_a_refusal_puts_a_new_request_up(d: BoundaryDaemon) -> None:
    _resolve(d, NAME)
    [refused] = d.pending()
    d.client.post(f"/api/v1/secrets/approvals/{refused['id']}/reject")

    asked = d.client.post("/api/v1/secrets/local-access/request", json={"name": NAME})

    assert asked.status_code == 200, asked.text
    assert asked.json()["local_access"] == "pending"
    [waiting] = d.pending()
    assert waiting["id"] != refused["id"] and waiting["destination_kind"] == "local_process"
    # Asking grants nothing: coffer run still waits for the person.
    assert _resolve(d, NAME).json()["error"]["code"] == "SECRET_BINDING_PENDING"
    assert FAKE not in _dumps(d)


@pytest.mark.acceptance(
    spec="secret", scenario="a granted secret reaches coffer run until the grant is withdrawn"
)
def test_a_grant_lets_the_value_out_and_revoking_withdraws_it(d: BoundaryDaemon) -> None:
    d.grant_local(NAME)
    row = {r["ref"]: r for r in d.client.get("/api/v1/secrets").json()["refs"]}[f"secret/{NAME}"]
    assert row["local_access"] == "on" and row["readable_by_local_processes"] is True

    granted = _resolve(d, NAME)
    assert granted.status_code == 200 and granted.json()["values"] == {NAME: FAKE}

    revoked = d.client.post("/api/v1/secrets/local-access/revoke", json={"name": NAME})
    assert revoked.status_code == 200 and revoked.json() == {
        "local_access": "off",
        "approval_id": None,
    }
    assert _resolve(d, NAME).status_code == 409
    assert len(d.audit("secret_local_access_revoked")) == 1
    row = {r["ref"]: r for r in d.client.get("/api/v1/secrets").json()["refs"]}[f"secret/{NAME}"]
    assert row["readable_by_local_processes"] is False


def test_a_listing_refresh_does_not_retire_a_waiting_request(d: BoundaryDaemon) -> None:
    """Approvals are refreshed against the configuration before each listing; a
    local-process request belongs to no configuration and must keep waiting."""
    d.client.post("/api/v1/secrets/local-access/request", json={"name": NAME})
    for _ in range(2):
        [waiting] = d.pending()
    assert waiting["destination_kind"] == "local_process"


def test_one_ungranted_name_refuses_the_whole_request(d: BoundaryDaemon) -> None:
    d.store("secret/other-key", "fake-other-value-123")
    d.grant_local(NAME)

    r = _resolve(d, NAME, "other-key")

    assert r.status_code == 409
    assert FAKE not in r.text and "fake-other-value-123" not in r.text
    assert d.audit("secret_resolved") == []


def test_a_resources_secret_cannot_be_granted(d: BoundaryDaemon) -> None:
    d.store("mcp_server/gh/TOKEN", "fake-resource-token-1")
    asked = d.client.post(
        "/api/v1/secrets/local-access/request", json={"name": "mcp_server/gh/TOKEN"}
    )
    unknown = d.client.post("/api/v1/secrets/local-access/request", json={"name": "nope"})
    assert asked.status_code == 422 and unknown.status_code == 404
    assert "fake-resource-token-1" not in asked.text + unknown.text


# --- the CLI ----------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="secret", scenario="coffer run without a grant starts nothing and prints no value"
)
def test_coffer_run_without_a_grant_starts_nothing(
    d: BoundaryDaemon, tmp_path: pathlib.Path
) -> None:
    marker = tmp_path / "child-ran"
    probe = f"import os, pathlib; pathlib.Path({str(marker)!r}).write_text(os.environ['K'])"

    result = _runner.invoke(
        cli_app, ["run", "--secret", f"K={NAME}", "--", sys.executable, "-c", probe]
    )

    assert result.exit_code != 0
    assert not marker.exists()
    assert FAKE not in result.output
    assert "Coffer app" in result.output


def test_a_reference_inherited_from_the_environment_needs_the_grant_too(
    d: BoundaryDaemon, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An agent can export `K=coffer://secret/<name>` instead of passing
    --secret; the same grant applies."""
    monkeypatch.setenv("K", f"coffer://secret/{NAME}")
    marker = tmp_path / "child-ran"
    probe = f"import pathlib; pathlib.Path({str(marker)!r}).write_text('x')"

    result = _runner.invoke(cli_app, ["run", "--", sys.executable, "-c", probe])

    assert result.exit_code != 0 and not marker.exists()
    assert FAKE not in result.output


def test_a_granted_value_lives_only_in_the_child(d: BoundaryDaemon) -> None:
    """The child (and what it starts) gets the value; the shell that ran
    `coffer run` does not, and the child's output is masked."""
    d.grant_local(NAME)
    probe = (
        "import os, subprocess, sys; "
        "print('grandchild', subprocess.run([sys.executable, '-c', "
        "'import os; print(os.environ[\"K\"])'], capture_output=True, text=True).stdout.strip())"
    )

    result = _runner.invoke(
        cli_app, ["run", "--secret", f"K={NAME}", "--", sys.executable, "-c", probe]
    )

    assert result.exit_code == 0, result.output
    assert "grandchild ***" in result.output
    assert FAKE not in result.output
    assert "K" not in os.environ or os.environ["K"] != FAKE


# --- errors and logs ----------------------------------------------------------------------


def test_no_refusal_or_grant_writes_the_value_to_a_log(
    d: BoundaryDaemon, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    _resolve(d, NAME)
    _runner.invoke(cli_app, ["run", "--secret", NAME, "--", sys.executable, "-c", "pass"])
    d.grant_local(NAME)
    d.client.post("/api/v1/secrets/local-access/revoke", json={"name": NAME})

    assert FAKE not in caplog.text
    assert FAKE not in _dumps(d)
    for path in (d.home / ".coffer").rglob("*"):
        if path.is_file() and path.stat().st_size < 5_000_000:
            assert FAKE.encode() not in path.read_bytes(), path


# --- the gateway path is unchanged -------------------------------------------------------


def test_an_approved_mcp_server_still_gets_its_secret_without_a_local_grant(
    d: BoundaryDaemon,
) -> None:
    """Using a secret through Coffer — the gateway injecting it into the server
    it was approved for — needs no local-process grant."""
    d.store("mcp_server/pm/KEY", "fake-gateway-key-123")
    server = d.register_stdio("pm", "postman-mcp", {"POSTMAN_API_KEY": "mcp_server/pm/KEY"})

    assert d.resolve_for(server) == {"POSTMAN_API_KEY": "fake-gateway-key-123"}
    assert _resolve(d, NAME).status_code == 409
