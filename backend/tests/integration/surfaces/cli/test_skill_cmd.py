"""Integration tests for `coffer skill` CLI subcommands.

Covers TEST21-015: every verb (`list` / `import` / `show` /
`enable` / `disable` / `rm` / `verify`) plus the `--json`
switch where it exists.

We boot the full FastAPI app (via ``create_app``) so the agent + skill
kinds are wired with the same cross-kind on_delete hook the production
daemon uses, then route ``_cli_client.client_or_exit`` to a Starlette
``TestClient`` against that app.

Booting the *whole* app is what keeps these tests working now that every verb
resolves the name it was given through ``GET /resources?kind=&name=`` before it
addresses ``/skills/{uid}`` or ``/agents/{uid}/...``
(ADR resource-identity-is-an-immutable-uid): an app mounting only the skill and
agent routers could no longer answer the first of those two requests. The verbs
still TAKE names — that is the point of resolving here rather than asking a
person to type a uid — so nothing below passes one.

The skill-manager spec §User Story 7 — every CLI verb mirrors the REST surface.
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
    r = _runner.invoke(cli_app, ["skill", "import", str(src)])
    assert r.exit_code == 0, r.output
    result = _runner.invoke(cli_app, ["skill", "list"])
    assert result.exit_code == 0, result.output
    assert "Skills" in result.output
    assert "hello-cli" in result.output


def _agent_uid(name: str) -> str:
    """The uid of the registered agent called ``name``, read back through the CLI.

    Tests need it to assert what is STORED, which is never what is printed —
    ``coffer resource show`` is the one verb that puts a uid on screen, exactly
    so a script (or a test) can act on a row it found by name.
    """
    r = _runner.invoke(cli_app, ["resource", "show", "agent", name, "--json"])
    assert r.exit_code == 0, r.output
    return str(json.loads(_extract_json(r.output))["uid"])


def test_skill_scope_prints_agent_names_while_storing_uids(skill_cli_daemon, monkeypatch):
    """The Scope column is agent NAMES; the stored scope is agent UIDS.

    This is the whole reason ``skill_cmd._agent_names`` fetches the agent
    listing at all. A scope holds uids because that is what a cross-resource
    reference is now (ADR resource-identity-is-an-immutable-uid), and a uid is
    an address, not information: if the translation silently regressed, both
    ``list`` and ``show`` would print a column of hex that matches nothing the
    user ever typed, and no other test would notice. So the assertion is made
    from both ends — the JSON body carries the uid, the rendered output carries
    the name and NOT the uid.
    """
    monkeypatch.setenv("COLUMNS", "200")  # don't let rich wrap the Scope cell apart
    _register_agent(skill_cli_daemon, "cur")
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="scoped-1")
    assert _runner.invoke(cli_app, ["skill", "import", str(src)]).exit_code == 0

    uid = _agent_uid("cur")
    # `scope set` takes the agent NAME too, and resolves it on the way in.
    r = _runner.invoke(cli_app, ["scope", "set", "skill", "scoped-1", "--agents", "cur"])
    assert r.exit_code == 0, r.output

    # What was stored: the uid, not the name.
    shown_json = _runner.invoke(cli_app, ["skill", "show", "scoped-1", "--json"])
    assert shown_json.exit_code == 0, shown_json.output
    assert json.loads(_extract_json(shown_json.output))["scope"]["agents"] == [uid]

    # What is printed: the name, and nowhere the uid.
    shown = _runner.invoke(cli_app, ["skill", "show", "scoped-1"])
    assert shown.exit_code == 0, shown.output
    assert "scope:       agents: cur" in shown.output
    assert uid not in shown.output

    listed = _runner.invoke(cli_app, ["skill", "list"])
    assert listed.exit_code == 0, listed.output
    assert "agents: cur" in listed.output
    assert uid not in listed.output


def test_skill_scope_prints_an_unmatched_uid_verbatim(skill_cli_daemon, monkeypatch):
    """A scope entry no agent answers to is shown as-is, not dropped.

    A stored scope may legitimately name an agent this machine does not have
    (the vault converges across machines; the scope is per-machine). Hiding
    such an entry would make the printed reach NARROWER than the one the daemon
    applies, so ``_scope_label`` falls back to the raw uid. Written through the
    HTTP surface because ``coffer scope set`` deliberately refuses a name that
    resolves to nothing — the only way to hold an unmatched uid is to already
    have one.
    """
    monkeypatch.setenv("COLUMNS", "200")
    _register_agent(skill_cli_daemon, "cur")
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="scoped-2")
    assert _runner.invoke(cli_app, ["skill", "import", str(src)]).exit_code == 0

    stray = "00000000000000000000000000000000"
    c, _info = _cli_client.client_or_exit()
    skill_uid = c.get("/resources", params={"kind": "skill", "name": "scoped-2"}).json()[
        "resources"
    ][0]["uid"]
    put = c.put(
        f"/resources/{skill_uid}/scope",
        json={"scope": {"agents": [_agent_uid("cur"), stray]}},
    )
    assert put.status_code == 200, put.text

    shown = _runner.invoke(cli_app, ["skill", "show", "scoped-2"])
    assert shown.exit_code == 0, shown.output
    assert f"scope:       agents: cur, {stray}" in shown.output


# ---------------------------------------------------------------------------
# skill import
# ---------------------------------------------------------------------------


def test_skill_import_success(skill_cli_daemon):
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="imp-1")
    result = _runner.invoke(cli_app, ["skill", "import", str(src)])
    assert result.exit_code == 0, result.output
    # The echo lost the ``<kind>:<name>`` form along with the string identity
    # the ADR deletes; the kind survives as a plain word.
    assert "imported: skill imp-1" in result.output


def test_skill_import_invalid_folder_exits_2(skill_cli_daemon):
    """A folder without a valid SKILL.md frontmatter exits non-zero."""
    bad = skill_cli_daemon / "bad"
    bad.mkdir()
    (bad / "SKILL.md").write_text("no frontmatter here")
    result = _runner.invoke(cli_app, ["skill", "import", str(bad)])
    assert result.exit_code == 2, result.output


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
    ``httpx.HTTPStatusError`` — while ``coffer resource delete
    skill:coffer-guide`` rendered it properly. Two doors onto the same refusal
    behaved differently; this pins them together.
    """
    r = _runner.invoke(cli_app, ["skill", "rm", "coffer-guide", "--force"])

    assert r.exception is None or isinstance(r.exception, SystemExit), r.exception
    # 5 == ExitCode.CONFLICT, the same code `resource delete` returns.
    assert r.exit_code == 5, r.output
    assert "is managed by Coffer" in r.output
    assert "Traceback" not in r.output

    # And the refusal stuck: the skill is still there.
    show = _runner.invoke(cli_app, ["skill", "show", "coffer-guide"])
    assert show.exit_code == 0, show.output


def test_skill_rm_and_resource_delete_agree_on_a_protected_skill(skill_cli_daemon):
    """The two CLI doors onto the same DELETE report the same thing."""
    via_skill = _runner.invoke(cli_app, ["skill", "rm", "coffer-guide", "--force"])
    via_resource = _runner.invoke(
        cli_app, ["resource", "delete", "skill", "coffer-guide", "--force"]
    )
    assert via_skill.exit_code == via_resource.exit_code
    assert "is managed by Coffer" in via_skill.output
    assert "is managed by Coffer" in via_resource.output


def test_skill_import_cannot_take_over_coffers_own_name(skill_cli_daemon):
    """``--force`` must not let an import claim a skill Coffer generates.

    Overwriting rewrote the row's ``source`` to ``local_import``, and the
    delete guard reads exactly that field — so the skill became deletable
    until the next boot seeded it back.
    """
    src = skill_cli_daemon / "impostor"
    _write_skill_folder(src, name="coffer-guide")

    r = _runner.invoke(cli_app, ["skill", "import", str(src), "--force"])
    assert r.exit_code != 0, r.output

    show = _runner.invoke(cli_app, ["skill", "show", "coffer-guide", "--json"])
    assert show.exit_code == 0, show.output
    assert json.loads(_extract_json(show.output))["source"] == {"type": "builtin"}


def test_skill_rm_without_force_aborts(skill_cli_daemon):
    """Without --force the prompt aborts on `n` and the skill remains."""
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="rm-2")
    _runner.invoke(cli_app, ["skill", "import", str(src)])
    r = _runner.invoke(cli_app, ["skill", "rm", "rm-2"], input="n\n")
    assert r.exit_code == 1
    show = _runner.invoke(cli_app, ["skill", "show", "rm-2"])
    assert show.exit_code == 0


# ---------------------------------------------------------------------------
# skill unmanaged / adopt / rm-unmanaged
# ---------------------------------------------------------------------------


def test_skill_unmanaged_list_json(skill_cli_daemon):
    """`skill unmanaged --json` lists skill-shaped folders Coffer doesn't manage."""
    skills_dir = _register_agent(skill_cli_daemon, "cur")
    _write_skill_folder(skills_dir / "loose-skill", name="loose-skill")

    r = _runner.invoke(cli_app, ["skill", "unmanaged", "cur", "--json"])
    assert r.exit_code == 0, r.output
    items = json.loads(_extract_json(r.output))
    assert len(items) == 1
    assert items[0]["name"] == "loose-skill"
    assert items[0]["valid"] is True
    assert items[0]["location"] == "skills"

    # Table path renders without crashing.
    r = _runner.invoke(cli_app, ["skill", "unmanaged", "cur"])
    assert r.exit_code == 0, r.output
    assert "loose-skill" in r.output


def test_skill_unmanaged_agent_not_found(skill_cli_daemon):
    """The AGENT argument resolves too, and an unknown one names its own kind."""
    r = _runner.invoke(cli_app, ["skill", "unmanaged", "ghost"])
    assert r.exit_code == 4, r.output
    assert "no agent named 'ghost'" in r.output


def test_skill_adopt_unmanaged(skill_cli_daemon):
    """`skill adopt` moves the folder into the master store and binds it."""
    skills_dir = _register_agent(skill_cli_daemon, "cur")
    _write_skill_folder(skills_dir / "adopt-me", name="adopt-me")

    r = _runner.invoke(cli_app, ["skill", "adopt", "cur", "adopt-me", "--location", "skills"])
    assert r.exit_code == 0, r.output
    assert "adopted: skill adopt-me" in r.output

    # The skill is now managed (visible in `skill show`) and no longer unmanaged.
    show = _runner.invoke(cli_app, ["skill", "show", "adopt-me"])
    assert show.exit_code == 0, show.output
    r = _runner.invoke(cli_app, ["skill", "unmanaged", "cur", "--json"])
    assert json.loads(_extract_json(r.output)) == []


def test_skill_rm_unmanaged(skill_cli_daemon):
    """`skill rm-unmanaged` prompts without --force; --force deletes from disk."""
    skills_dir = _register_agent(skill_cli_daemon, "cur")
    folder = _write_skill_folder(skills_dir / "junk-skill", name="junk-skill")

    r = _runner.invoke(cli_app, ["skill", "rm-unmanaged", "cur", "junk-skill"], input="n\n")
    assert r.exit_code == 1
    assert folder.exists()

    r = _runner.invoke(cli_app, ["skill", "rm-unmanaged", "cur", "junk-skill", "--force"])
    assert r.exit_code == 0, r.output
    assert "deleted: unmanaged skill junk-skill (agent cur)" in r.output
    assert not folder.exists()


# ---------------------------------------------------------------------------
# skill verify --fix
# ---------------------------------------------------------------------------


def test_skill_verify_fix_repairs_and_reports(skill_cli_daemon):
    """--fix re-delivers MISSING_LINK and reports remaining drift."""
    skills_dir = _register_agent(skill_cli_daemon, "cur")
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="fix-1")
    _runner.invoke(cli_app, ["skill", "import", str(src)])

    link = skills_dir / "fix-1"
    assert link.exists()

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
    skills_dir = _register_agent(skill_cli_daemon, "cur")
    src = skill_cli_daemon / "src"
    _write_skill_folder(src, name="foreign-1")
    _runner.invoke(cli_app, ["skill", "import", str(src)])

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


@pytest.mark.acceptance(
    spec="skill-manager", scenario="manage unmanaged skills from the skill command group"
)
def test_unmanaged_skill_operations_live_under_coffer_skill(skill_cli_daemon):
    """List, adopt and delete unmanaged skills through `coffer skill`, never `coffer agent`."""
    import typer.main

    skills_dir = _register_agent(skill_cli_daemon, "cur")
    _write_skill_folder(skills_dir / "keep-me", name="keep-me")
    junk = _write_skill_folder(skills_dir / "drop-me", name="drop-me")

    r = _runner.invoke(cli_app, ["skill", "unmanaged", "cur", "--json"])
    assert r.exit_code == 0, r.output
    assert sorted(i["name"] for i in json.loads(_extract_json(r.output))) == [
        "drop-me",
        "keep-me",
    ]

    r = _runner.invoke(cli_app, ["skill", "adopt", "cur", "keep-me"])
    assert r.exit_code == 0, r.output
    assert (skills_dir / "keep-me").is_symlink()
    assert _runner.invoke(cli_app, ["skill", "show", "keep-me"]).exit_code == 0

    r = _runner.invoke(cli_app, ["skill", "rm-unmanaged", "cur", "drop-me", "--force"])
    assert r.exit_code == 0, r.output
    assert not junk.exists()

    r = _runner.invoke(cli_app, ["skill", "unmanaged", "cur", "--json"])
    assert json.loads(_extract_json(r.output)) == []

    # The agent is an argument to these operations, not their subject.
    agent_group = typer.main.get_command(cli_app).commands["agent"]  # type: ignore[attr-defined]
    assert "config" in agent_group.commands
    assert not {"unmanaged", "adopt", "rm-unmanaged"} & set(agent_group.commands)


# ---------------------------------------------------------------------------
# skill files / cat / write — the master folder from a terminal
# ---------------------------------------------------------------------------


def _import_with_nested_file(home: pathlib.Path, name: str) -> pathlib.Path:
    """Import a skill carrying ``refs/notes.txt``; hand back its master folder."""
    src = _write_skill_folder(home / f"src-{name}", name=name)
    (src / "refs").mkdir()
    (src / "refs" / "notes.txt").write_text("first\n", encoding="utf-8")
    r = _runner.invoke(cli_app, ["skill", "import", str(src)])
    assert r.exit_code == 0, r.output
    show = _runner.invoke(cli_app, ["skill", "show", name, "--json"])
    return pathlib.Path(json.loads(_extract_json(show.output))["master_path"])


def _walk(node: dict) -> list[tuple[str, str]]:  # type: ignore[type-arg]
    out = [(node["path"], node["type"])]
    for child in node["children"]:
        out.extend(_walk(child))
    return out


@pytest.mark.acceptance(spec="skill-manager", scenario="desktop and CLI cover every operation")
def test_skill_files_lists_the_master_folder_tree(skill_cli_daemon):
    _import_with_nested_file(skill_cli_daemon, "tree-1")

    as_json = _runner.invoke(cli_app, ["skill", "files", "tree-1", "--json"])
    as_text = _runner.invoke(cli_app, ["skill", "files", "tree-1"])

    assert as_json.exit_code == 0, as_json.output
    root = json.loads(_extract_json(as_json.output))["root"]
    assert _walk(root) == [
        ("", "dir"),
        ("refs", "dir"),
        ("refs/notes.txt", "file"),
        (".coffer.meta.json", "file"),
        ("SKILL.md", "file"),
    ]
    assert as_text.exit_code == 0, as_text.output
    assert "refs/notes.txt" in as_text.output
    assert "SKILL.md" in as_text.output


@pytest.mark.acceptance(spec="skill-manager", scenario="desktop and CLI cover every operation")
def test_skill_cat_prints_the_file_and_its_fingerprint(skill_cli_daemon):
    import hashlib

    master = _import_with_nested_file(skill_cli_daemon, "cat-1")

    plain = _runner.invoke(cli_app, ["skill", "cat", "cat-1", "refs/notes.txt"])
    as_json = _runner.invoke(cli_app, ["skill", "cat", "cat-1", "refs/notes.txt", "--json"])

    assert plain.exit_code == 0, plain.output
    assert plain.output.endswith("first\n")
    assert as_json.exit_code == 0, as_json.output
    data = json.loads(_extract_json(as_json.output))
    assert data["content"] == "first\n"
    raw = (master / "refs" / "notes.txt").read_bytes()
    assert data["fingerprint"] == hashlib.sha256(raw).hexdigest()


def test_skill_cat_of_a_missing_file_exits_4(skill_cli_daemon):
    _import_with_nested_file(skill_cli_daemon, "cat-2")

    r = _runner.invoke(cli_app, ["skill", "cat", "cat-2", "refs/absent.txt"])

    assert r.exit_code == 4, r.output
    assert "no such file in skill: refs/absent.txt" in r.output


def test_skill_cat_outside_the_folder_is_refused(skill_cli_daemon):
    _import_with_nested_file(skill_cli_daemon, "cat-3")

    r = _runner.invoke(cli_app, ["skill", "cat", "cat-3", "../../etc/passwd"])

    assert r.exit_code == 6, r.output
    assert "outside the skill folder" in r.output


@pytest.mark.acceptance(spec="skill-manager", scenario="desktop and CLI cover every operation")
def test_skill_write_from_stdin_saves_the_file(skill_cli_daemon):
    master = _import_with_nested_file(skill_cli_daemon, "wr-1")

    r = _runner.invoke(cli_app, ["skill", "write", "wr-1", "refs/notes.txt"], input="second\n")

    assert r.exit_code == 0, r.output
    assert (master / "refs" / "notes.txt").read_text(encoding="utf-8") == "second\n"
    back = _runner.invoke(cli_app, ["skill", "cat", "wr-1", "refs/notes.txt"])
    assert back.output.endswith("second\n")


def test_skill_write_from_file_saves_the_file(skill_cli_daemon):
    master = _import_with_nested_file(skill_cli_daemon, "wr-2")
    new = skill_cli_daemon / "new.txt"
    new.write_text("from a file\n", encoding="utf-8")

    r = _runner.invoke(
        cli_app, ["skill", "write", "wr-2", "refs/notes.txt", "--from-file", str(new)]
    )

    assert r.exit_code == 0, r.output
    assert (master / "refs" / "notes.txt").read_text(encoding="utf-8") == "from a file\n"


@pytest.mark.acceptance(spec="skill-manager", scenario="reject a stale save of a skill file")
def test_skill_write_with_a_stale_fingerprint_exits_5_and_leaves_the_file(skill_cli_daemon):
    master = _import_with_nested_file(skill_cli_daemon, "wr-3")
    read = _runner.invoke(cli_app, ["skill", "cat", "wr-3", "refs/notes.txt", "--json"])
    seen = json.loads(_extract_json(read.output))["fingerprint"]
    # Someone edits the file in their own editor after that read.
    (master / "refs" / "notes.txt").write_text("edited elsewhere\n", encoding="utf-8")

    r = _runner.invoke(
        cli_app,
        ["skill", "write", "wr-3", "refs/notes.txt", "--fingerprint", seen],
        input="my buffer\n",
    )

    assert r.exit_code == 5, r.output
    assert "changed on disk since last read" in r.output
    assert (master / "refs" / "notes.txt").read_text(encoding="utf-8") == "edited elsewhere\n"


def test_skill_write_to_coffers_own_skill_is_refused(skill_cli_daemon):
    show = _runner.invoke(cli_app, ["skill", "show", "coffer-guide", "--json"])
    master = pathlib.Path(json.loads(_extract_json(show.output))["master_path"])
    before = (master / "SKILL.md").read_bytes()

    r = _runner.invoke(cli_app, ["skill", "write", "coffer-guide", "SKILL.md"], input="mine\n")

    assert r.exit_code == 5, r.output
    assert "is managed by Coffer" in r.output
    assert "rewritten from the running build" in " ".join(r.output.split())
    assert (master / "SKILL.md").read_bytes() == before


def test_skill_file_commands_on_an_unknown_skill_exit_4(skill_cli_daemon):
    for argv in (
        ["skill", "files", "ghost"],
        ["skill", "cat", "ghost", "SKILL.md"],
        ["skill", "write", "ghost", "SKILL.md"],
    ):
        r = _runner.invoke(cli_app, argv, input="x")
        assert r.exit_code == 4, (argv, r.output)
        assert "no skill named 'ghost'" in r.output


@pytest.mark.acceptance(
    spec="skill-manager", scenario="an empty or interactive `skill write` saves nothing"
)
def test_skill_write_with_empty_stdin_is_refused_and_leaves_the_file(skill_cli_daemon):
    """stdin at EOF (cron, CI, an agent's shell, ``</dev/null``) reads as "" —
    that is never taken as the new content unless ``--allow-empty`` says so."""
    master = _import_with_nested_file(skill_cli_daemon, "wr-empty")

    r = _runner.invoke(cli_app, ["skill", "write", "wr-empty", "refs/notes.txt"], input="")

    assert r.exit_code == 2, r.output
    assert "no content" in r.output
    assert "--allow-empty" in r.output
    assert "saved:" not in r.output
    assert (master / "refs" / "notes.txt").read_text(encoding="utf-8") == "first\n"


@pytest.mark.acceptance(
    spec="skill-manager", scenario="an empty or interactive `skill write` saves nothing"
)
def test_skill_write_of_an_empty_file_is_refused_too(skill_cli_daemon):
    master = _import_with_nested_file(skill_cli_daemon, "wr-empty-f")
    empty = skill_cli_daemon / "empty.txt"
    empty.write_text("", encoding="utf-8")

    r = _runner.invoke(
        cli_app, ["skill", "write", "wr-empty-f", "refs/notes.txt", "--from-file", str(empty)]
    )

    assert r.exit_code == 2, r.output
    assert (master / "refs" / "notes.txt").read_text(encoding="utf-8") == "first\n"


@pytest.mark.acceptance(
    spec="skill-manager", scenario="an empty or interactive `skill write` saves nothing"
)
def test_skill_write_allow_empty_empties_the_file(skill_cli_daemon):
    master = _import_with_nested_file(skill_cli_daemon, "wr-empty-ok")

    r = _runner.invoke(
        cli_app,
        ["skill", "write", "wr-empty-ok", "refs/notes.txt", "--allow-empty"],
        input="",
    )

    assert r.exit_code == 0, r.output
    assert "saved: refs/notes.txt" in r.output
    assert (master / "refs" / "notes.txt").read_text(encoding="utf-8") == ""


@pytest.mark.acceptance(
    spec="skill-manager", scenario="an empty or interactive `skill write` saves nothing"
)
def test_skill_write_from_a_terminal_without_from_file_is_a_usage_error(
    skill_cli_daemon, monkeypatch
):
    """With stdin a terminal, reading it would sit silently until EOF; the
    command refuses up front instead, before it reads anything."""
    import coffer.surfaces.cli.skill_file_cmd as skill_file_cmd

    master = _import_with_nested_file(skill_cli_daemon, "wr-tty")
    monkeypatch.setattr(skill_file_cmd, "_stdin_is_tty", lambda: True)

    r = _runner.invoke(
        cli_app, ["skill", "write", "wr-tty", "refs/notes.txt"], input="never read\n"
    )

    assert r.exit_code == 2, r.output
    assert "--from-file" in r.output
    assert "terminal" in r.output
    assert (master / "refs" / "notes.txt").read_text(encoding="utf-8") == "first\n"


def test_skill_write_from_a_terminal_with_from_file_still_writes(skill_cli_daemon, monkeypatch):
    import coffer.surfaces.cli.skill_file_cmd as skill_file_cmd

    master = _import_with_nested_file(skill_cli_daemon, "wr-tty-f")
    monkeypatch.setattr(skill_file_cmd, "_stdin_is_tty", lambda: True)
    new = skill_cli_daemon / "tty-new.txt"
    new.write_text("typed elsewhere\n", encoding="utf-8")

    r = _runner.invoke(
        cli_app, ["skill", "write", "wr-tty-f", "refs/notes.txt", "--from-file", str(new)]
    )

    assert r.exit_code == 0, r.output
    assert (master / "refs" / "notes.txt").read_text(encoding="utf-8") == "typed elsewhere\n"


def _import_with_big_file(home: pathlib.Path, name: str) -> tuple[pathlib.Path, int]:
    """Import a skill whose ``refs/big.txt`` is past the route's read cap."""
    src = _write_skill_folder(home / f"src-{name}", name=name)
    (src / "refs").mkdir()
    size = 300 * 1024
    (src / "refs" / "big.txt").write_text("a" * size, encoding="utf-8")
    r = _runner.invoke(cli_app, ["skill", "import", str(src)])
    assert r.exit_code == 0, r.output
    show = _runner.invoke(cli_app, ["skill", "show", name, "--json"])
    return pathlib.Path(json.loads(_extract_json(show.output))["master_path"]), size


@pytest.mark.acceptance(
    spec="skill-manager", scenario="a truncated `skill cat` does not pass for the whole file"
)
def test_skill_cat_of_a_truncated_file_exits_1_and_says_so(skill_cli_daemon):
    """A partial print is not a successful read: a script piping ``cat`` into a
    file would otherwise keep the first 256 KiB and carry on."""
    _import_with_big_file(skill_cli_daemon, "cat-big")

    r = _runner.invoke(cli_app, ["skill", "cat", "cat-big", "refs/big.txt"])

    assert r.exit_code == 1, r.output[-300:]
    assert f"truncated: the file is {300 * 1024} bytes" in r.output
    assert "a" * 1000 in r.output


@pytest.mark.acceptance(
    spec="skill-manager", scenario="a truncated `skill cat` does not pass for the whole file"
)
def test_skill_cat_json_of_a_truncated_file_exits_0_with_the_flag(skill_cli_daemon):
    _import_with_big_file(skill_cli_daemon, "cat-big-j")

    r = _runner.invoke(cli_app, ["skill", "cat", "cat-big-j", "refs/big.txt", "--json"])

    assert r.exit_code == 0, r.output[-300:]
    data = json.loads(_extract_json(r.output))
    assert data["truncated"] is True
    assert data["size"] == 300 * 1024
    assert len(data["content"]) == 256 * 1024
