"""Integration tests for `coffer skill` CLI subcommands.

Covers TEST21-015: every verb (`list` / `import` / `fetch` / `show` /
`enable` / `disable` / `rm` / `update` / `verify`) plus the `--json`
switch where it exists.

We boot the full FastAPI app (via ``create_app``) so the agent + skill
kinds are wired with the same cross-kind on_delete hook the production
daemon uses, then route ``_cli_client.client_or_exit`` to a Starlette
``TestClient`` against that app.

The 005-skill-manager spec §User Story 7 — every CLI verb mirrors the REST surface.
"""

from __future__ import annotations

import json
import pathlib
import textwrap
from datetime import UTC
from datetime import datetime as dt

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

# mix_stderr=False so alembic/INFO logs from the in-process app lifespan
# don't get mingled with the CLI's stdout — JSON-parsing tests rely on
# stdout being only the JSON body the CLI verb printed.
_runner = CliRunner()
_TOKEN = "test-token-skill-cli"


def _extract_json(output: str) -> str:
    """Strip leading log lines so JSON can be decoded.

    The in-process FastAPI lifespan emits alembic INFO logs (which contain
    ``[alembic.runtime.migration] ...``) to the same captured stream as the
    CLI's stdout under CliRunner. Skip whole log lines and return from the
    first line whose first character is a JSON sentinel (``[`` or ``{``).
    """
    lines = output.splitlines(keepends=True)
    for i, line in enumerate(lines):
        # The CLI's JSON output is always at the start of a line; alembic
        # logs always start with ``INFO ``/``WARN ``/``ERROR ``.
        if line and line[0] in "[{":
            return "".join(lines[i:])
    return output


def _write_skill_folder(folder: pathlib.Path, *, name: str) -> pathlib.Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        textwrap.dedent(
            f"""\
            ---
            name: {name}
            description: A test skill named {name}.
            ---

            body
            """
        ),
        encoding="utf-8",
    )
    return folder


@pytest.fixture
def skill_cli_daemon(tmp_path, monkeypatch):
    """In-process daemon (real `create_app`) plumbed through the CLI client.

    Yields the temp HOME path so individual tests can stage skill folders
    + agent config_dirs underneath it.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59700")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59709")

    app = create_app()
    set_active_token(_TOKEN)

    info = DaemonInfo(
        version=1,
        pid=12345,
        port=59700,
        token=_TOKEN,
        started_at=dt.now(tz=UTC),
        binary_path="/test",
    )

    # raise_server_exceptions=False so HTTPException → JSON envelope path
    # is exercised rather than re-raised through the test client.
    fake_client = TestClient(
        app,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "cli"},
        raise_server_exceptions=False,
    )

    # Open the underlying app's lifespan once so the wiring task
    # (auto-detect) doesn't leak between tests. The CLI verbs use
    # ``with c:`` semantics; each verb call would tear down the TestClient
    # at exit which closes the lifespan and drops the wired services.
    # Wrap the TestClient so ``__enter__``/``__exit__`` become no-ops while
    # the underlying object's lifecycle stays bound to this fixture.
    fake_client.__enter__()

    class _PersistentClient:
        """Thin proxy so the CLI's ``with c:`` block does NOT close the app."""

        def __init__(self, inner: TestClient) -> None:
            self._inner = inner

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            # Intentionally no-op; teardown lives in the fixture.
            return None

        def __getattr__(self, item):  # type: ignore[no-untyped-def]
            return getattr(self._inner, item)

    monkeypatch.setattr(
        _cli_client,
        "client_or_exit",
        lambda: (_PersistentClient(fake_client), info),
    )

    yield tmp_path

    fake_client.__exit__(None, None, None)
    set_active_token(None)


def _register_agent(home: pathlib.Path, name: str) -> pathlib.Path:
    """Register an agent via the CLI; return where its skills are delivered.

    The agent model uses ``config_dir``; registration auto-creates
    ``<config_dir>/skills`` and that is where enabled skills land. We return
    that delivery dir so link-location assertions stay correct.
    """
    config_dir = home / f"{name}-cfg"
    config_dir.mkdir()
    r = _runner.invoke(
        cli_app,
        ["agent", "add", "claude_code", "--name", name, "--config-dir", str(config_dir)],
    )
    assert r.exit_code == 0, r.output
    return config_dir / "skills"


# ---------------------------------------------------------------------------
# skill list
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="005-skill-manager", scenario="desktop and CLI cover every operation")
def test_skill_list_empty_json(skill_cli_daemon):
    """`skill list --json` is an empty JSON array when no skills exist."""
    result = _runner.invoke(cli_app, ["skill", "list", "--json"])
    assert result.exit_code == 0, result.output
    items = json.loads(_extract_json(result.output))
    assert items == []


def test_skill_list_table_default(skill_cli_daemon):
    """`skill list` renders the rich table without crashing."""
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="hello-cli")
    r = _runner.invoke(cli_app, ["skill", "import", str(src)])
    assert r.exit_code == 0, r.output
    result = _runner.invoke(cli_app, ["skill", "list"])
    assert result.exit_code == 0, result.output
    assert "Skills" in result.output
    assert "hello-cli" in result.output


# ---------------------------------------------------------------------------
# skill import
# ---------------------------------------------------------------------------


def test_skill_import_success(skill_cli_daemon):
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="imp-1")
    result = _runner.invoke(cli_app, ["skill", "import", str(src)])
    assert result.exit_code == 0, result.output
    assert "imported" in result.output
    assert "imp-1" in result.output


def test_skill_import_invalid_folder_exits_2(skill_cli_daemon):
    """A folder without a valid SKILL.md frontmatter exits non-zero."""
    bad = skill_cli_daemon / "bad"
    bad.mkdir()
    (bad / "SKILL.md").write_text("no frontmatter here")
    result = _runner.invoke(cli_app, ["skill", "import", str(bad)])
    assert result.exit_code == 2, result.output


# ---------------------------------------------------------------------------
# skill fetch
# ---------------------------------------------------------------------------


def test_skill_fetch_ssrf_rejected(skill_cli_daemon):
    """SSRF guard prevents fetch from loopback hosts — exits non-zero."""
    result = _runner.invoke(
        cli_app,
        ["skill", "fetch", "http://127.0.0.1/repo.git", "--ref", "main"],
    )
    assert result.exit_code == 2, result.output
    # The envelope message is surfaced on stderr.
    assert "SSRF" in (result.output or "") or "127.0.0.1" in (result.output or "")


# ---------------------------------------------------------------------------
# skill show
# ---------------------------------------------------------------------------


def test_skill_show_text(skill_cli_daemon):
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="shw-1")
    _runner.invoke(cli_app, ["skill", "import", str(src)])
    result = _runner.invoke(cli_app, ["skill", "show", "shw-1"])
    assert result.exit_code == 0, result.output
    assert "shw-1" in result.output
    assert "name:" in result.output


def test_skill_show_json(skill_cli_daemon):
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="shw-2")
    _runner.invoke(cli_app, ["skill", "import", str(src)])
    result = _runner.invoke(cli_app, ["skill", "show", "shw-2", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(_extract_json(result.output))
    assert data["name"] == "shw-2"
    assert "version_hash" in data


def test_skill_show_not_found(skill_cli_daemon):
    result = _runner.invoke(cli_app, ["skill", "show", "ghost"])
    assert result.exit_code == 4, result.output


# ---------------------------------------------------------------------------
# skill enable / disable
# ---------------------------------------------------------------------------


def test_skill_enable_then_disable(skill_cli_daemon):
    """enable creates a link, disable removes it."""
    skills_dir = _register_agent(skill_cli_daemon, "cur")
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="ed-1")
    _runner.invoke(cli_app, ["skill", "import", str(src)])
    # Import auto-binds; explicit enable is still a valid (idempotent) verb.
    r = _runner.invoke(cli_app, ["skill", "enable", "ed-1", "--agent", "cur"])
    assert r.exit_code == 0, r.output
    # Skills land at <config_dir>/skills/<skill>.
    link = skills_dir / "ed-1"
    assert link.exists()

    r = _runner.invoke(cli_app, ["skill", "disable", "ed-1", "--agent", "cur"])
    assert r.exit_code == 0, r.output
    assert not link.exists()


# ---------------------------------------------------------------------------
# skill update
# ---------------------------------------------------------------------------


def test_skill_update_local_import_not_supported(skill_cli_daemon):
    """`update` on a local_import-sourced skill is rejected (re-import required)."""
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="up-1")
    _runner.invoke(cli_app, ["skill", "import", str(src)])
    r = _runner.invoke(cli_app, ["skill", "update", "up-1"])
    # ExitCode.GENERIC (2) — surface routes 4xx through `_cli_client.check`
    # but the import side defers to the typer.Exit(2) raised in `update_cmd`.
    assert r.exit_code != 0


# ---------------------------------------------------------------------------
# skill verify
# ---------------------------------------------------------------------------


def test_skill_verify_no_drift_text(skill_cli_daemon):
    """`verify` prints `no drift` and exits 0 when bindings are clean."""
    skills_dir = _register_agent(skill_cli_daemon, "cur")
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="vfy-1")
    _runner.invoke(cli_app, ["skill", "import", str(src)])
    assert (skills_dir / "vfy-1").exists()
    r = _runner.invoke(cli_app, ["skill", "verify"])
    assert r.exit_code == 0, r.output
    assert "no drift" in r.output


def test_skill_verify_drift_exits_2(skill_cli_daemon):
    """Once a link is missing, `verify` exits non-zero and reports the drift."""
    skills_dir = _register_agent(skill_cli_daemon, "cur")
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="vfy-2")
    _runner.invoke(cli_app, ["skill", "import", str(src)])
    (skills_dir / "vfy-2").unlink()
    r = _runner.invoke(cli_app, ["skill", "verify"])
    assert r.exit_code == 2, r.output
    assert "vfy-2" in r.output


def test_skill_verify_json(skill_cli_daemon):
    """`verify --json` prints a JSON array and exits 0 when clean."""
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="vfy-3")
    _runner.invoke(cli_app, ["skill", "import", str(src)])
    r = _runner.invoke(cli_app, ["skill", "verify", "--json"])
    assert r.exit_code == 0, r.output
    data = json.loads(_extract_json(r.output))
    assert isinstance(data, list)


# ---------------------------------------------------------------------------
# skill rm
# ---------------------------------------------------------------------------


def test_skill_rm_force(skill_cli_daemon):
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="rm-1")
    _runner.invoke(cli_app, ["skill", "import", str(src)])
    r = _runner.invoke(cli_app, ["skill", "rm", "rm-1", "--force"])
    assert r.exit_code == 0, r.output
    assert "removed" in r.output
    # And the show is gone.
    show = _runner.invoke(cli_app, ["skill", "show", "rm-1"])
    assert show.exit_code == 4


def test_skill_rm_not_found(skill_cli_daemon):
    r = _runner.invoke(cli_app, ["skill", "rm", "ghost", "--force"])
    assert r.exit_code == 4, r.output


def test_skill_rm_without_force_aborts(skill_cli_daemon):
    """Without --force the prompt aborts on `n` and the skill remains."""
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="rm-2")
    _runner.invoke(cli_app, ["skill", "import", str(src)])
    r = _runner.invoke(cli_app, ["skill", "rm", "rm-2"], input="n\n")
    assert r.exit_code == 1
    show = _runner.invoke(cli_app, ["skill", "show", "rm-2"])
    assert show.exit_code == 0
