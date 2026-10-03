"""An attention item's hand-off on the wire and through ``coffer attention``.

The wire shape is ``attention_item_out`` over real items; the command runs
against a fake client serving that same shape, so what it prints is compared
with what the route would serve.
"""

from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner

from coffer.application.attention import (
    AttentionAction,
    AttentionItem,
    AttentionReport,
    Severity,
)
from coffer.surfaces.cli import _client as cli_client
from coffer.surfaces.cli.main import app as cli
from coffer.surfaces.http.reconcile_schemas import attention_out

runner = CliRunner()

PROMPT = "Please install `uvx` on this machine.\n\n- Needed by the MCP server fetch."


def _item(uid: str, handoff: str | None) -> AttentionItem:
    return AttentionItem(
        kind="mcp_server",
        uid=uid,
        title=uid,
        reason_code="mcp_missing_launcher",
        reason="Its launcher uvx isn't found on this machine.",
        severity=Severity.ERROR,
        action=AttentionAction("test", "POST", f"/api/v1/resources/mcp_server/{uid}/test"),
        handoff=handoff,
    )


def _body() -> dict[str, Any]:
    report = AttentionReport(
        items=(_item("fetch", PROMPT), _item("plain", None)), counts_by_kind={"mcp_server": 2}
    )
    return attention_out(report).model_dump(mode="json")


class _Response:
    status_code = 200

    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body

    def json(self) -> dict[str, Any]:
        return self._body


class _Client:
    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body

    def __enter__(self) -> _Client:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def get(self, _path: str) -> _Response:
        return _Response(self._body)


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    body = _body()
    monkeypatch.setattr(cli_client, "client_or_exit", lambda: (_Client(body), None))
    monkeypatch.setattr(cli_client, "check", lambda *_a, **_k: None)
    return body


@pytest.mark.acceptance(spec="resource-framework", scenario="every item carries a hand-off prompt")
def test_the_command_prints_the_route_s_prompt_for_any_item(
    served: dict[str, Any],
) -> None:
    fetch, plain = served["items"]
    assert fetch["handoff"] == {"prompt": PROMPT}
    assert plain["handoff"]["prompt"] and plain["handoff"]["prompt"] != PROMPT

    out = runner.invoke(cli, ["attention", "--prompt", fetch["key"]])
    assert out.exit_code == 0, out.output
    assert out.output == PROMPT + "\n"

    out = runner.invoke(cli, ["attention", "--prompt", plain["key"]])
    assert out.exit_code == 0, out.output
    assert out.output == plain["handoff"]["prompt"] + "\n"


def test_the_table_points_at_the_prompt_and_an_unknown_key_is_not_found(
    served: dict[str, Any],
) -> None:
    out = runner.invoke(cli, ["attention"])
    assert out.exit_code == 0, out.output
    assert "coffer attention --prompt" in out.output

    out = runner.invoke(cli, ["attention", "--prompt", "mcp_server:gone:x"])
    assert out.exit_code == 4
