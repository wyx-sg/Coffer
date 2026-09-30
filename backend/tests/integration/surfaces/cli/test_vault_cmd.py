"""``coffer vault history | diff | show | restore | problems``
(coffer.surfaces.cli.vault_cmd; spec vault-storage "Show, compare and
restore any version of a vault file").

The CLI client is pointed at the vault router over this test's own HOME, so
each command runs the route it names against a real vault repository.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.domain.vault.writers import WRITER_USER, CommitMeta
from coffer.domain.vault.writes import Expect
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.infrastructure.vault.home import vault_root
from coffer.infrastructure.vault.instance import vault_repository, vault_writer
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_actor, get_audit_service
from coffer.surfaces.http.vault_routes import router as vault_router

_runner = CliRunner()
_TOKEN = "t-vault-cli"
USER = CommitMeta(writer=WRITER_USER, operation="edit", summary="Saved", actor="ui")


class _Audit:
    async def record(self, event_type: str, **_: Any) -> None:
        return None


class _Persistent:
    def __init__(self, inner: TestClient) -> None:
        self._inner = inner

    def __enter__(self) -> _Persistent:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def __getattr__(self, item: str) -> Any:
        return getattr(self._inner, item)


@pytest.fixture(autouse=True)
def daemon(monkeypatch: pytest.MonkeyPatch) -> Any:
    set_active_token(_TOKEN)
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(vault_router)
    app.dependency_overrides[get_audit_service] = lambda: _Audit()
    app.dependency_overrides[get_actor] = lambda: "cli"
    client = TestClient(app, base_url="http://localhost/api/v1", headers={"X-Coffer-Token": _TOKEN})
    info = DaemonInfo(
        version=1,
        pid=1,
        port=1,
        token=_TOKEN,
        started_at=datetime.now(tz=UTC),
        binary_path="/test",
    )
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (_Persistent(client), info))
    with client:
        yield


def _two_versions() -> tuple[str, str]:
    first = vault_writer().write_file(
        "skills/pdf/SKILL.md", b"v1\n", meta=USER, expected=Expect.ABSENT
    )
    second = vault_writer().write_file("skills/pdf/SKILL.md", b"v2\n", meta=USER)
    assert first and second
    return first, second


def test_history_lists_versions_newest_first() -> None:
    first, second = _two_versions()
    r = _runner.invoke(cli_app, ["vault", "history", "skills/pdf/SKILL.md", "--json"])
    assert r.exit_code == 0, r.output
    versions = json.loads(r.output)["versions"]
    assert [v["version"] for v in versions] == [second, first]
    table = _runner.invoke(cli_app, ["vault", "history", "skills/pdf/"])
    assert table.exit_code == 0, table.output
    assert second[:10] in table.output and "you" in table.output


def test_diff_and_show_print_a_version() -> None:
    first, second = _two_versions()
    diff = _runner.invoke(cli_app, ["vault", "diff", "skills/pdf/SKILL.md", second])
    assert diff.exit_code == 0, diff.output
    assert "-v1" in diff.output and "+v2" in diff.output
    show = _runner.invoke(cli_app, ["vault", "show", "skills/pdf/SKILL.md", first])
    assert show.exit_code == 0 and show.output == "v1\n"


def test_restore_reads_the_current_fingerprint_first() -> None:
    first, _second = _two_versions()
    r = _runner.invoke(cli_app, ["vault", "restore", "skills/pdf/SKILL.md", first, "--yes"])
    assert r.exit_code == 0, r.output
    assert (vault_root() / "skills/pdf/SKILL.md").read_bytes() == b"v1\n"
    assert vault_repository().log(limit=1)[0].meta.restored_from == first
    again = _runner.invoke(cli_app, ["vault", "restore", "skills/pdf/SKILL.md", first, "--yes"])
    assert "nothing to restore" in again.output


def test_restore_asks_before_writing() -> None:
    first, _second = _two_versions()
    r = _runner.invoke(cli_app, ["vault", "restore", "skills/pdf/", first], input="n\n")
    assert r.exit_code == 1
    assert (vault_root() / "skills/pdf/SKILL.md").read_bytes() == b"v2\n"


@pytest.mark.acceptance(
    spec="vault-storage", scenario="refused hand edits are listed on REST and the command line"
)
def test_problems_lists_refused_hand_edits() -> None:
    empty = _runner.invoke(cli_app, ["vault", "problems"])
    assert empty.exit_code == 0 and "no problems" in empty.output
    r = _runner.invoke(cli_app, ["vault", "problems", "--json"])
    assert json.loads(r.output) == {"problems": []}
