"""Integration tests for `coffer agent transcripts`.

FR-044/FR-046 require every agent-workspace op to exist on BOTH REST and CLI;
this verb wraps the one read-only route:

  ``GET /agents/{uid}/transcripts`` → ``transcripts``

The verb still TAKES a name; the route is addressed by uid
(ADR resource-identity-is-an-immutable-uid). So every invocation is now two
requests, in this order: ``GET /resources?kind=agent&name=<name>`` to turn what
the user typed into a uid, then the transcript route under that uid. The fake
client below serves the first from a ``name -> uid`` registry and the second
from the canned map, which is what makes the uid in every path assertion below
predictable.

Like the rest of the CLI suite we stub the HTTP layer: a tiny fake client
returns canned ``GET`` responses and ``_client.client_or_exit`` is
monkeypatched to hand it back. No daemon, and — importantly — no walk of the
developer's real ``~/.claude`` / ``~/.codex`` transcripts.
"""

from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime as dt
from typing import Any

from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli.main import app as cli_app

_runner = CliRunner()

#: The uid the fake registry hands back for the agent named ``cx``. Opaque on
#: purpose — nothing in the CLI may derive it from the name.
CX_UID = "6f1c0b8a4d5e4a1cb2f39e77c0a15d34"

SESSION = {
    "session_id": "a1",
    "title": "fix the alpha login bug",
    "project_path": "/proj/alpha",
    "message_count": 12,
    "started_at": "2026-05-01T09:30:00Z",
    "last_activity_at": "2026-05-09T18:05:00Z",
    "source_path": "/home/u/.codex/sessions/2026/05/rollout-a1.jsonl",
}


class _FakeResponse:
    """Minimal stand-in for ``httpx.Response`` as the CLI consumes it."""

    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = b"x"

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:  # pragma: no cover - not exercised
            import httpx

            request = httpx.Request("GET", "http://test/")
            raise httpx.HTTPStatusError(
                "error",
                request=request,
                response=httpx.Response(self.status_code, json=self._payload, request=request),
            )


class _FakeClient:
    """Records GET calls and replays canned responses keyed by path.

    It also stands in for the resource registry, because every agent command
    now starts by asking it for a uid. ``agents`` is the ``name -> uid`` table
    that ``GET /resources?kind=agent&name=`` is answered from; a name missing
    from it produces the empty match list a real daemon would return, which is
    how a test says "no such agent" without registering a 404 route.
    """

    def __init__(self, get_map: dict[str, _FakeResponse], agents: dict[str, str]):
        self._get_map = get_map
        self._agents = agents
        self.calls: list[tuple[str, str, Any]] = []

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def get(self, path: str, **kw: Any) -> _FakeResponse:
        self.calls.append(("GET", path, kw))
        if path == "/resources":
            return self._resolve(kw.get("params") or {})
        return self._get_map[path]

    def _resolve(self, params: dict[str, Any]) -> _FakeResponse:
        """The name → uid lookup, shaped exactly like the real list route."""
        name = params.get("name")
        uid = self._agents.get(str(name))
        matches = [] if uid is None else [{"uid": uid, "kind": params.get("kind"), "name": name}]
        return _FakeResponse(200, {"resources": matches})


def _install(monkeypatch, *, get_map=None, agents=None) -> _FakeClient:
    """Install the fake client. ``agents`` defaults to the one agent the
    happy-path tests use; pass ``{}`` for a registry that holds nobody."""
    client = _FakeClient(get_map or {}, {"cx": CX_UID} if agents is None else agents)
    info = DaemonInfo(
        version=1,
        pid=1,
        port=8000,
        token="t",
        started_at=dt.now(tz=UTC),
        binary_path="/t",
    )
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (client, info))
    return client


def _page(sessions: list[dict[str, Any]], total: int | None = None) -> _FakeResponse:
    return _FakeResponse(
        200,
        {
            "sessions": sessions,
            "total": total if total is not None else len(sessions),
            "limit": 20,
            "offset": 0,
        },
    )


def test_transcripts_json(monkeypatch):
    """`transcripts <name> --json` prints the raw response verbatim."""
    _install(monkeypatch, get_map={f"/agents/{CX_UID}/transcripts": _page([SESSION], total=3)})

    result = _runner.invoke(cli_app, ["agent", "transcripts", "cx", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "sessions": [SESSION],
        "total": 3,
        "limit": 20,
        "offset": 0,
    }


def test_transcripts_table(monkeypatch):
    """`transcripts <name>` renders title, project, count, and short times."""
    monkeypatch.setenv("COLUMNS", "200")  # don't let rich wrap the assertions apart
    _install(monkeypatch, get_map={f"/agents/{CX_UID}/transcripts": _page([SESSION], total=3)})

    result = _runner.invoke(cli_app, ["agent", "transcripts", "cx"])
    assert result.exit_code == 0, result.output
    assert "fix the alpha login bug" in result.output
    assert "/proj/alpha" in result.output
    assert "12" in result.output
    assert "2026-05-01 09:30" in result.output  # seconds trimmed for the table
    assert "1 of 3" in result.output  # page size vs matched total


def test_transcripts_untitled_row_falls_back_to_session_id(monkeypatch):
    """A session the agent never titled still identifies itself in the table."""
    monkeypatch.setenv("COLUMNS", "200")
    untitled = {**SESSION, "title": None, "started_at": None, "last_activity_at": None}
    _install(monkeypatch, get_map={f"/agents/{CX_UID}/transcripts": _page([untitled])})

    result = _runner.invoke(cli_app, ["agent", "transcripts", "cx"])
    assert result.exit_code == 0, result.output
    assert "a1" in result.output


def test_transcripts_forwards_query_sort_and_paging(monkeypatch):
    """Search/sort/paging options travel as query params, not client-side.

    The recorded calls also pin the two-step shape: the name is resolved first,
    by the one route allowed to look a resource up by its label, and only then
    is the transcript route addressed — under the uid that lookup returned, not
    under the name the user typed.
    """
    client = _install(monkeypatch, get_map={f"/agents/{CX_UID}/transcripts": _page([SESSION])})

    result = _runner.invoke(
        cli_app,
        [
            "agent",
            "transcripts",
            "cx",
            "-q",
            "alpha",
            "--sort",
            "started_at",
            "--order",
            "asc",
            "--limit",
            "5",
            "--offset",
            "10",
        ],
    )
    assert result.exit_code == 0, result.output
    assert client.calls == [
        ("GET", "/resources", {"params": {"kind": "agent", "name": "cx"}}),
        (
            "GET",
            f"/agents/{CX_UID}/transcripts",
            {
                "params": {
                    "limit": 5,
                    "offset": 10,
                    "sort": "started_at",
                    "order": "asc",
                    "q": "alpha",
                }
            },
        ),
    ]


def test_transcripts_unknown_agent_exits_4(monkeypatch):
    """A name nobody holds exits 4 before any transcript route is touched.

    The exit code is unchanged, but the refusal moved: it used to be a 404 from
    the transcript route, and it is now the name → uid lookup finding nothing
    (``_resolve.resolve``). That matters for the message — it names the kind and
    the string the user typed, which a 404 on an opaque uid could not do — and
    it is why ``client.calls`` stops after the lookup.
    """
    client = _install(monkeypatch, agents={})

    result = _runner.invoke(cli_app, ["agent", "transcripts", "ghost"])
    assert result.exit_code == 4, result.output
    assert "no agent named 'ghost'" in result.output
    assert client.calls == [("GET", "/resources", {"params": {"kind": "agent", "name": "ghost"}})]


def test_transcripts_is_registered():
    """The read verb appears under `coffer agent` (FR-044 CLI/REST parity)."""
    help_out = _runner.invoke(cli_app, ["agent", "--help"]).output
    assert "transcripts" in help_out
