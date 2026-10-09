"""``coffer update`` and ``coffer uninstall`` (spec daemon "Upgrade the installed
binaries from the command line" and "Uninstall Coffer from this machine").

The daemon is replaced by a recorder of the requests the commands make, so the
tests read which routes a command reached and in what order.
"""

from __future__ import annotations

import pathlib
from typing import Any

import pytest
from typer.testing import CliRunner

from coffer.surfaces.cli import _desktop, _io, lifecycle_cmd
from coffer.surfaces.cli.main import app

_runner = CliRunner()


class Daemon:
    def __init__(self, method: str) -> None:
        self.method = method
        self.calls: list[tuple[str, str, Any]] = []

    def call(self, method: str, path: str, *, as_json: bool, body: Any = None, **_: Any) -> Any:
        self.calls.append((method, path, body))
        if path == "/daemon/upgrade":
            return {"install_method": self.method}
        if path == "/daemon/uninstall":
            return {
                "ok": True,
                "deletes_data": False,
                "steps": [{"key": "binaries", "outcome": "done", "detail": "/h/.coffer/bin"}],
            }
        raise AssertionError(f"unexpected {method} {path}")


@pytest.fixture
def daemon(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> Daemon:
    monkeypatch.setenv("HOME", str(tmp_path))
    d = Daemon("binaries")
    monkeypatch.setattr(_io, "call", d.call)
    monkeypatch.setattr(lifecycle_cmd, "_wait_for_exit", lambda: True)
    return d


@pytest.mark.acceptance(
    spec="daemon", scenario="the command line will not delete the data without a terminal"
)
def test_delete_data_without_a_terminal_refuses_whatever_else_is_given(
    daemon: Daemon, tmp_path: pathlib.Path
) -> None:
    (tmp_path / ".coffer").mkdir()
    r = _runner.invoke(app, ["uninstall", "--delete-data", "--yes"])
    assert r.exit_code == 2, r.output
    assert "delete my data" in r.output
    assert [c[1] for c in daemon.calls] == ["/daemon/upgrade"]
    assert (tmp_path / ".coffer").exists()


def test_uninstall_without_a_terminal_needs_yes(daemon: Daemon) -> None:
    refused = _runner.invoke(app, ["uninstall"])
    assert refused.exit_code == 2
    assert [c[1] for c in daemon.calls] == ["/daemon/upgrade"]
    done = _runner.invoke(app, ["uninstall", "--yes"])
    assert done.exit_code == 0, done.output
    assert ("POST", "/daemon/uninstall", {}) in daemon.calls
    assert "remove ~/.coffer/bin" in done.output


def test_with_the_desktop_app_both_commands_go_to_the_app(
    daemon: Daemon, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon.method = "app"
    sent: list[dict[str, Any]] = []

    def run(body: dict[str, Any], **_: Any) -> dict[str, Any]:
        sent.append(body)
        return {"status": "done", "result": {"phase": "upToDate"}}

    monkeypatch.setattr(_desktop, "run", run)
    assert _runner.invoke(app, ["uninstall", "--delete-data"]).exit_code == 0
    assert _runner.invoke(app, ["update"]).exit_code == 0
    assert sent == [{"op": "uninstall", "enabled": True}, {"op": "update_install"}]
    assert not any(c[1] == "/daemon/uninstall" for c in daemon.calls)


def test_a_source_checkout_is_told_to_pull(daemon: Daemon) -> None:
    daemon.method = "source"
    r = _runner.invoke(app, ["update"])
    assert r.exit_code == 2
    assert "git pull" in r.output
