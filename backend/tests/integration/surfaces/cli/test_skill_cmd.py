"""Integration tests for `coffer skill` CLI subcommands.

Covers every verb of the group — `list`, `show`, `add <folder>`, `edit`, `rm`,
`enable`, `disable`, `scope` and `verify` (spec skill-manager "Cover skill
management on REST, the CLI and the web") — plus `--json` on every read.
Unmanaged skills are `coffer scan|adopt|discard` (test_scan_cmd.py), and the
master folder is `coffer path skill` (test_path_cmd.py).

We boot the full FastAPI app (via ``create_app``) so the agent + skill
kinds are wired with the same cross-kind on_delete hook the production
daemon uses, then route ``_cli_client.client_or_exit`` to a Starlette
``TestClient`` against that app.

Booting the *whole* app is what keeps these tests working now that every verb
resolves the name it was given through ``GET /resources?kind=&name=`` before it
addresses ``/skills/{uid}`` or ``/agents/{uid}/...``
(ADR identity-is-the-uid-inside-the-file): an app mounting only the skill and
agent routers could no longer answer the first of those two requests. The verbs
still TAKE names — that is the point of resolving here rather than asking a
person to type a uid — so nothing below passes one.

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
from tests.support.reconcile import quiet_background_repair

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


def _register_agent(home: pathlib.Path, agent_type: str = "claude-code") -> pathlib.Path:
    """Register the agent of ``agent_type`` via the CLI; return where its
    skills are delivered.

    An agent is named by its type, so ``agent_type`` is also the name the
    tests type afterwards. Registration auto-creates ``<config_dir>/skills``
    and that is where enabled skills land.
    """
    config_dir = home / f"{agent_type}-cfg"
    config_dir.mkdir()
    r = _runner.invoke(cli_app, ["agent", "add", agent_type, "--config-dir", str(config_dir)])
    assert r.exit_code == 0, r.output
    return config_dir / "skills"


# ---------------------------------------------------------------------------
# skill list
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="skill-manager", scenario="desktop and CLI cover every operation")
def test_skill_list_json_holds_only_coffers_own_on_a_fresh_vault(skill_cli_daemon):
    """`skill list --json` before the user imports anything.

    Exactly one row, and it is Coffer's: the manual it seeds for itself (spec
    knowledge "Deliver the catalogue through the coffer-guide skill"). It is an
    ordinary skill Resource, which is precisely why
    it appears here — the rendering it replaced was written straight into each
    agent's own directory and this listing never knew about it.
    """
    result = _runner.invoke(cli_app, ["skill", "list", "--json"])
    assert result.exit_code == 0, result.output
    items = json.loads(_extract_json(result.output))
    assert [i["name"] for i in items] == ["coffer-guide"]
    assert items[0]["source"] == {"type": "builtin"}


def test_skill_list_table_default(skill_cli_daemon):
    """`skill list` renders the rich table without crashing."""
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="hello-cli")
    r = _runner.invoke(cli_app, ["skill", "add", str(src)])
    assert r.exit_code == 0, r.output
    result = _runner.invoke(cli_app, ["skill", "list"])
    assert result.exit_code == 0, result.output
    assert "Skills" in result.output
    assert "hello-cli" in result.output


def _agent_uid(name: str) -> str:
    """The uid of the registered agent called ``name``, read over REST.

    Tests need it to assert what is STORED, which is never what is printed.
    """
    c, _info = _cli_client.client_or_exit()
    r = c.get("/resources", params={"kind": "agent", "name": name})
    assert r.status_code == 200, r.text
    return str(r.json()["resources"][0]["uid"])


def test_skill_scope_prints_agent_names_while_storing_uids(skill_cli_daemon, monkeypatch):
    """The Scope column is agent NAMES; the stored scope is agent UIDS.

    This is the whole reason ``skill_cmd._agent_names`` fetches the agent
    listing at all. A scope holds uids because that is what a cross-resource
    reference is now (ADR identity-is-the-uid-inside-the-file), and a uid is
    an address, not information: if the translation silently regressed, both
    ``list`` and ``show`` would print a column of hex that matches nothing the
    user ever typed, and no other test would notice. So the assertion is made
    from both ends — the JSON body carries the uid, the rendered output carries
    the name and NOT the uid.
    """
    monkeypatch.setenv("COLUMNS", "200")  # don't let rich wrap the Scope cell apart
    _register_agent(skill_cli_daemon)
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="scoped-1")
    assert _runner.invoke(cli_app, ["skill", "add", str(src)]).exit_code == 0

    uid = _agent_uid("claude-code")
    # `skill scope` takes the agent NAME too, and resolves it on the way in.
    r = _runner.invoke(cli_app, ["skill", "scope", "scoped-1", "--agents", "claude-code"])
    assert r.exit_code == 0, r.output

    # What was stored: the uid, not the name.
    shown_json = _runner.invoke(cli_app, ["skill", "show", "scoped-1", "--json"])
    assert shown_json.exit_code == 0, shown_json.output
    assert json.loads(_extract_json(shown_json.output))["scope"]["agents"] == [uid]

    # What is printed: the name, and nowhere the uid.
    shown = _runner.invoke(cli_app, ["skill", "show", "scoped-1"])
    assert shown.exit_code == 0, shown.output
    assert "scope:       agents: claude-code" in shown.output
    assert uid not in shown.output

    listed = _runner.invoke(cli_app, ["skill", "list"])
    assert listed.exit_code == 0, listed.output
    assert "agents: claude-code" in listed.output
    assert uid not in listed.output


def test_skill_scope_prints_an_unmatched_uid_verbatim(skill_cli_daemon, monkeypatch):
    """A scope entry no agent answers to is shown as-is, not dropped.

    A stored scope may legitimately name an agent this machine does not have
    (the vault converges across machines; the scope is per-machine). Hiding
    such an entry would make the printed reach NARROWER than the one the daemon
    applies, so ``_scope_label`` falls back to the raw uid. Written through the
    HTTP surface because ``coffer skill scope`` deliberately refuses a name that
    resolves to nothing — the only way to hold an unmatched uid is to already
    have one.
    """
    monkeypatch.setenv("COLUMNS", "200")
    _register_agent(skill_cli_daemon)
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="scoped-2")
    assert _runner.invoke(cli_app, ["skill", "add", str(src)]).exit_code == 0

    stray = "00000000000000000000000000000000"
    c, _info = _cli_client.client_or_exit()
    skill_uid = c.get("/resources", params={"kind": "skill", "name": "scoped-2"}).json()[
        "resources"
    ][0]["uid"]
    put = c.put(
        f"/resources/{skill_uid}/scope",
        json={"scope": {"agents": [_agent_uid("claude-code"), stray]}},
    )
    assert put.status_code == 200, put.text

    shown = _runner.invoke(cli_app, ["skill", "show", "scoped-2"])
    assert shown.exit_code == 0, shown.output
    assert f"scope:       agents: claude-code, {stray}" in shown.output


# ---------------------------------------------------------------------------
# skill add <folder>
# ---------------------------------------------------------------------------


def test_skill_add_success(skill_cli_daemon):
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="imp-1")
    result = _runner.invoke(cli_app, ["skill", "add", str(src)])
    assert result.exit_code == 0, result.output
    assert "added: skill imp-1" in result.output


def test_skill_add_invalid_folder_exits_6(skill_cli_daemon):
    """A folder without a valid SKILL.md frontmatter is refused as invalid input."""
    bad = skill_cli_daemon / "bad"
    bad.mkdir()
    (bad / "SKILL.md").write_text("no frontmatter here")
    result = _runner.invoke(cli_app, ["skill", "add", str(bad)])
    assert result.exit_code == 6, result.output


# ---------------------------------------------------------------------------
# skill show
# ---------------------------------------------------------------------------


def test_skill_show_text(skill_cli_daemon):
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="shw-1")
    _runner.invoke(cli_app, ["skill", "add", str(src)])
    result = _runner.invoke(cli_app, ["skill", "show", "shw-1"])
    assert result.exit_code == 0, result.output
    assert "shw-1" in result.output
    assert "name:" in result.output


def test_skill_show_json(skill_cli_daemon):
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="shw-2")
    _runner.invoke(cli_app, ["skill", "add", str(src)])
    result = _runner.invoke(cli_app, ["skill", "show", "shw-2", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(_extract_json(result.output))
    assert data["name"] == "shw-2"
    assert "version_hash" in data


def test_skill_show_not_found(skill_cli_daemon):
    """A name nobody holds exits 4 — from the lookup, not from ``/skills``.

    Same exit code the 404 branch used to produce, but the refusal now happens
    one step earlier, in ``_resolve.resolve``, before a uid exists to address a
    route with. The message is asserted because it is the part that changed: it
    names the kind and the exact string typed, which is the whole reason the
    resolution is done at the surface the person is standing at.
    """
    result = _runner.invoke(cli_app, ["skill", "show", "ghost"])
    assert result.exit_code == 4, result.output
    assert "no skill named 'ghost'" in result.output


# ---------------------------------------------------------------------------
# skill verify
# ---------------------------------------------------------------------------


def test_skill_verify_no_drift_text(skill_cli_daemon):
    """`verify` prints `no drift` and exits 0 when bindings are clean."""
    skills_dir = _register_agent(skill_cli_daemon)
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="vfy-1")
    _runner.invoke(cli_app, ["skill", "add", str(src)])
    assert (skills_dir / "vfy-1").exists()
    r = _runner.invoke(cli_app, ["skill", "verify"])
    assert r.exit_code == 0, r.output
    assert "no drift" in r.output


def test_skill_verify_drift_exits_2(skill_cli_daemon, monkeypatch):
    """Once a link is missing, `verify` exits non-zero and reports the drift."""
    skills_dir = _register_agent(skill_cli_daemon)
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="vfy-2")
    _runner.invoke(cli_app, ["skill", "add", str(src)])
    quiet_background_repair(monkeypatch)
    (skills_dir / "vfy-2").unlink()
    r = _runner.invoke(cli_app, ["skill", "verify"])
    assert r.exit_code == 2, r.output
    assert "vfy-2" in r.output


def test_skill_verify_json(skill_cli_daemon):
    """`verify --json` prints a JSON array and exits 0 when clean."""
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="vfy-3")
    _runner.invoke(cli_app, ["skill", "add", str(src)])
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
    _runner.invoke(cli_app, ["skill", "add", str(src)])
    r = _runner.invoke(cli_app, ["skill", "rm", "rm-1", "--force"])
    assert r.exit_code == 0, r.output
    assert "removed: skill rm-1" in r.output
    # And the show is gone.
    show = _runner.invoke(cli_app, ["skill", "show", "rm-1"])
    assert show.exit_code == 4


def test_skill_rm_not_found(skill_cli_daemon):
    """Deleting a name nobody holds is refused by the lookup, before any DELETE."""
    r = _runner.invoke(cli_app, ["skill", "rm", "ghost", "--force"])
    assert r.exit_code == 4, r.output
    assert "no skill named 'ghost'" in r.output


def test_skill_rm_of_coffers_own_reports_the_refusal(skill_cli_daemon):
    """A protected skill must come back as a message, not a traceback.

    ``coffer skill rm`` used to call ``r.raise_for_status()`` bare, so the 409
    the server answers for a builtin skill escaped as an unhandled
    ``httpx.HTTPStatusError``. `rm` is now the lifecycle verb every kind
    shares, and the refusal must still come back rendered.
    """
    r = _runner.invoke(cli_app, ["skill", "rm", "coffer-guide", "--force"])

    assert r.exception is None or isinstance(r.exception, SystemExit), r.exception
    # 5 == ExitCode.CONFLICT.
    assert r.exit_code == 5, r.output
    assert "is managed by Coffer" in r.output
    assert "Traceback" not in r.output

    # And the refusal stuck: the skill is still there.
    show = _runner.invoke(cli_app, ["skill", "show", "coffer-guide"])
    assert show.exit_code == 0, show.output


def test_skill_add_cannot_take_over_coffers_own_name(skill_cli_daemon):
    """``--force`` must not let an import claim a skill Coffer generates.

    Overwriting rewrote the row's ``source`` to ``local_import``, and the
    delete guard reads exactly that field — so the skill became deletable
    until the next boot seeded it back.
    """
    src = skill_cli_daemon / "impostor"
    _write_skill_folder(src, name="coffer-guide")

    r = _runner.invoke(cli_app, ["skill", "add", str(src), "--force"])
    assert r.exit_code != 0, r.output

    show = _runner.invoke(cli_app, ["skill", "show", "coffer-guide", "--json"])
    assert show.exit_code == 0, show.output
    assert json.loads(_extract_json(show.output))["source"] == {"type": "builtin"}


def test_skill_rm_without_force_aborts(skill_cli_daemon):
    """Without --force the prompt aborts on `n` and the skill remains."""
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="rm-2")
    _runner.invoke(cli_app, ["skill", "add", str(src)])
    r = _runner.invoke(cli_app, ["skill", "rm", "rm-2"], input="n\n")
    assert r.exit_code == 1
    show = _runner.invoke(cli_app, ["skill", "show", "rm-2"])
    assert show.exit_code == 0


# ---------------------------------------------------------------------------
# an unmanaged skill, previewed on disk
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="skill-manager", scenario="read an unmanaged skill's files from the command line"
)
def test_scan_names_an_unmanaged_folder_that_is_then_read_on_disk(skill_cli_daemon):
    """`coffer scan --agent --json` reports the unmanaged folder with its absolute
    path; its files are read there, and reading adopts nothing."""
    skills_dir = _register_agent(skill_cli_daemon)
    folder = _write_skill_folder(skills_dir / "loose-skill", name="loose-skill")
    (folder / "refs").mkdir()
    (folder / "refs" / "a.txt").write_text("alpha\n", encoding="utf-8")

    def skill_rows() -> list[dict]:
        r = _runner.invoke(cli_app, ["scan", "--agent", "claude-code", "--json"])
        assert r.exit_code == 0, r.output
        return [
            row for row in json.loads(_extract_json(r.output))["rows"] if row["kind"] == "skill"
        ]

    (row,) = skill_rows()
    assert row["name"] == "loose-skill"
    assert row["valid"] is True
    root = pathlib.Path(row["ref"])
    assert root.is_absolute()
    assert sorted(p.relative_to(root).as_posix() for p in root.rglob("*")) == [
        "SKILL.md",
        "refs",
        "refs/a.txt",
    ]
    assert (root / "refs" / "a.txt").read_text(encoding="utf-8") == "alpha\n"

    # Still unmanaged: reading adopted nothing.
    assert [r["name"] for r in skill_rows()] == ["loose-skill"]


# ---------------------------------------------------------------------------
# skill verify --fix
# ---------------------------------------------------------------------------


def test_skill_verify_fix_repairs_and_reports(skill_cli_daemon, monkeypatch):
    """--fix re-delivers MISSING_LINK and reports remaining drift."""
    skills_dir = _register_agent(skill_cli_daemon)
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="fix-1")
    _runner.invoke(cli_app, ["skill", "add", str(src)])

    link = skills_dir / "fix-1"
    assert link.exists()
    quiet_background_repair(monkeypatch)

    # Introduce MISSING_LINK drift.
    link.unlink()

    r = _runner.invoke(cli_app, ["skill", "verify", "--fix"])
    # Link is restored.
    assert link.exists(), "repair should restore the missing link"
    # Output shows repaired section.
    assert "Repaired" in r.output or "fix-1" in r.output, r.output
    # No remaining manual drift → exit 0.
    assert r.exit_code == 0, r.output


def test_skill_verify_fix_remaining_exits_2(skill_cli_daemon):
    """--fix exits 2 when unrepairable drift remains."""
    skills_dir = _register_agent(skill_cli_daemon)
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="foreign-1")
    _runner.invoke(cli_app, ["skill", "add", str(src)])

    link = skills_dir / "foreign-1"
    assert link.is_symlink()
    # Replace symlink with a real directory → REPLACED_WITH_REGULAR.
    link.unlink()
    link.mkdir()
    (link / "intruder.txt").write_text("not managed by coffer")

    r = _runner.invoke(cli_app, ["skill", "verify", "--fix"])
    # Still drifted section visible.
    assert "Still drifted" in r.output or "foreign-1" in r.output, r.output
    # Exit 2 because manual drift remains.
    assert r.exit_code == 2, r.output


# ---------------------------------------------------------------------------
# the lifecycle verbs: scope / enable / disable / edit
# ---------------------------------------------------------------------------


def _skill_trail(name: str) -> list[str]:
    """The skill's own audit trail, oldest first, as event types."""
    c, _info = _cli_client.client_or_exit()
    uid = c.get("/resources", params={"kind": "skill", "name": name}).json()["resources"][0]["uid"]
    r = c.get("/audit", params={"resource_uid": uid, "limit": 500})
    assert r.status_code == 200, r.text
    return [e["event_type"] for e in reversed(r.json()["entries"])]


@pytest.mark.acceptance(
    spec="skill-manager", scenario="switch and scope a skill from its own command group"
)
def test_scope_disable_and_enable_a_skill_from_the_skill_group(skill_cli_daemon):
    first = _register_agent(skill_cli_daemon, "claude-code")
    second = _register_agent(skill_cli_daemon, "codex")
    _write_skill_folder(skill_cli_daemon / "src", name="switch-me")
    assert _runner.invoke(cli_app, ["skill", "add", str(skill_cli_daemon / "src")]).exit_code == 0
    assert (first / "switch-me").is_symlink() and (second / "switch-me").is_symlink()

    scoped = _runner.invoke(cli_app, ["skill", "scope", "switch-me", "--agents", "claude-code"])
    assert scoped.exit_code == 0, scoped.output
    assert "reach: claude-code" in scoped.output
    assert (first / "switch-me").is_symlink()
    assert not (second / "switch-me").exists()

    disabled = _runner.invoke(cli_app, ["skill", "disable", "switch-me"])
    assert disabled.exit_code == 0, disabled.output
    assert not (first / "switch-me").exists() and not (second / "switch-me").exists()

    enabled = _runner.invoke(cli_app, ["skill", "enable", "switch-me"])
    assert enabled.exit_code == 0, enabled.output
    assert (first / "switch-me").is_symlink()
    assert not (second / "switch-me").exists()

    trail = _skill_trail("switch-me")
    changes = [e for e in trail if e.startswith("resource_") and e != "resource_created"]
    assert changes == ["resource_scope_updated", "resource_disabled", "resource_enabled"]


@pytest.mark.acceptance(spec="skill-manager", scenario="desktop and CLI cover every operation")
@pytest.mark.acceptance(spec="resource-framework", scenario="a kind without a title refuses one")
def test_the_skill_group_is_the_lifecycle_verbs_and_the_folder_is_a_path(skill_cli_daemon):
    """The group offers the shared verbs plus `add`, `update` and `verify` — no `edit`,
    since a skill has nothing on its record to edit — every read
    takes `--json`, and the master folder is named by `coffer path skill`
    rather than listed, printed or written through the group."""
    import typer.main

    src = _write_skill_folder(skill_cli_daemon / "src", name="every-op")
    assert _runner.invoke(cli_app, ["skill", "add", str(src)]).exit_code == 0

    group = typer.main.get_command(cli_app).commands["skill"]  # type: ignore[attr-defined]
    assert list(group.commands) == [
        "list",
        "show",
        "add",
        "update",
        "rm",
        "enable",
        "disable",
        "scope",
        "verify",
    ]
    assert not {
        "import",
        "files",
        "cat",
        "write",
        "edit",
        "unmanaged",
        "adopt",
        "rm-unmanaged",
    } & set(group.commands)
    for read in (["list"], ["show", "every-op"], ["scope", "every-op"], ["verify"]):
        r = _runner.invoke(cli_app, ["skill", *read, "--json"])
        assert r.exit_code == 0, (read, r.output)
        json.loads(_extract_json(r.output))

    shown = json.loads(
        _extract_json(_runner.invoke(cli_app, ["skill", "show", "every-op", "--json"]).output)
    )
    path = _runner.invoke(cli_app, ["path", "skill", "every-op"])
    assert path.exit_code == 0, path.output
    assert path.output.strip().splitlines()[-1] == shown["master_path"]
    assert (pathlib.Path(shown["master_path"]) / "SKILL.md").is_file()


def test_skill_show_takes_a_uid_as_well_as_a_name(skill_cli_daemon):
    src = _write_skill_folder(skill_cli_daemon / "src", name="by-uid")
    assert _runner.invoke(cli_app, ["skill", "add", str(src)]).exit_code == 0
    uid = json.loads(
        _extract_json(_runner.invoke(cli_app, ["skill", "show", "by-uid", "--json"]).output)
    )["uid"]

    r = _runner.invoke(cli_app, ["skill", "show", uid, "--json"])

    assert r.exit_code == 0, r.output
    assert json.loads(_extract_json(r.output))["name"] == "by-uid"


@pytest.mark.acceptance(
    spec="skill-manager", scenario="a skill's title is edited without touching disk"
)
def test_a_skill_shows_its_name_and_carries_no_title(skill_cli_daemon, monkeypatch):
    """The CLI half of the scenario: a title for a skill has nowhere to go —
    `coffer skill` has no `edit`, `list` shows the name and `show --json`
    carries no `title` — and the folder and link are untouched."""
    monkeypatch.setenv("COLUMNS", "200")
    skills_dir = _register_agent(skill_cli_daemon)
    src = _write_skill_folder(skill_cli_daemon / "src", name="before")
    assert _runner.invoke(cli_app, ["skill", "add", str(src)]).exit_code == 0
    master = pathlib.Path(
        json.loads(
            _extract_json(_runner.invoke(cli_app, ["skill", "show", "before", "--json"]).output)
        )["master_path"]
    )
    skill_md = (master / "SKILL.md").read_bytes()
    link_target = (skills_dir / "before").resolve()

    r = _runner.invoke(cli_app, ["skill", "edit", "before", "--title", "Release checklist"])

    assert r.exit_code == 2, r.output  # no such command
    listed = _runner.invoke(cli_app, ["skill", "list"])
    assert "before" in listed.output
    assert "Release checklist" not in listed.output
    data = json.loads(
        _extract_json(_runner.invoke(cli_app, ["skill", "show", "before", "--json"]).output)
    )
    assert data["name"] == "before"
    assert "title" not in data
    assert (master / "SKILL.md").read_bytes() == skill_md
    assert (skills_dir / "before").resolve() == link_target
