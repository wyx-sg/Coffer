"""The lifecycle-verb factory (``surfaces/cli/_kind_verbs.py``).

Registered on a throwaway Typer tree over the ``in_proc_daemon`` fixture's two
test kinds: ``fake_kind`` (no reach) and ``fake_scoped`` (reach).
What is under test is the factory — that every group it builds offers the same
verbs over the kind-agnostic routes — not any real kind.
"""

from __future__ import annotations

import inspect
import json
from typing import Any

import pytest
import typer
from pydantic import BaseModel, ConfigDict
from typer.testing import CliRunner

from coffer.domain.resource import Kind
from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._kind_verbs import (
    ALL_VERBS,
    Column,
    EditFlags,
    KindVerbs,
    label,
    register_kind_verbs,
)
from coffer.surfaces.http.dependencies import get_resource_service

_runner = CliRunner()


def _tree() -> typer.Typer:
    root = typer.Typer()

    @root.callback()
    def _root(ctx: typer.Context) -> None:
        ctx.ensure_object(dict)

    plain = typer.Typer()
    register_kind_verbs(
        plain,
        KindVerbs(
            kind="fake_kind",
            noun="fake",
            columns=(Column("Foo", lambda r: str(r["config"].get("foo"))),),
            edit_flags=EditFlags(
                params=[
                    inspect.Parameter(
                        "foo",
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        default=typer.Option(None, "--foo"),
                        annotation=int | None,
                    )
                ],
                to_config=lambda r, v: (
                    None if v["foo"] is None else {**r["config"], "foo": v["foo"]}
                ),
            ),
        ),
    )
    scoped = typer.Typer()
    register_kind_verbs(
        scoped,
        KindVerbs(
            kind="fake_scoped",
            noun="scoped thing",
            verbs=frozenset(ALL_VERBS),
            name_fixed=True,
        ),
    )
    root.add_typer(plain, name="fake")
    root.add_typer(scoped, name="scoped")
    return root


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="allow")


def _client() -> Any:
    client, _info = _cli_client.client_or_exit()
    return client


def _register(kind: str, name: str, config: dict[str, Any]) -> str:
    r = _client().post("/resources", json={"kind": kind, "name": name, "config": config})
    assert r.status_code == 201, r.text
    return str(r.json()["uid"])


def _agent(name: str) -> str:
    svc = _client().app.dependency_overrides[get_resource_service]()
    svc._kinds.setdefault("agent", Kind(name="agent", display_name="Agent", config_schema=_Lenient))
    return _register("agent", name, {})


def _commands(app: typer.Typer, group: str) -> set[str]:
    cmd = typer.main.get_command(app)
    return set(cmd.commands[group].commands)  # type: ignore[attr-defined]


def _audit(event: str) -> list[dict[str, Any]]:
    r = _client().get("/audit", params={"event_type": event})
    assert r.status_code == 200, r.text
    return list(r.json()["entries"])


@pytest.mark.acceptance(
    spec="resource-framework", scenario="every kind's group offers the same lifecycle verbs"
)
def test_every_group_offers_the_same_verbs_and_disable_takes_name_or_uid(
    in_proc_daemon: Any,
) -> None:
    app = _tree()
    assert _commands(app, "fake") == {"list", "show", "edit", "rm", "enable", "disable"}
    assert _commands(app, "scoped") == set(ALL_VERBS)
    # A kind that cannot be disabled offers no switch (knowledge, memory).
    from coffer.surfaces.cli.main import app as cli_app

    for group in ("knowledge", "memory"):
        assert not {"enable", "disable"} & _commands(cli_app, group)
    # `add` is never generated: only a kind that registers its own offers it,
    # and a partition is created only by aggregation.
    assert "add" not in _commands(app, "scoped")
    assert "add" not in _commands(cli_app, "memory")
    # `edit` only where the kind has something to edit — a skill's name is
    # fixed, it has no title and its description is its SKILL.md's — and
    # `--title` only on a kind that carries one.
    assert "edit" not in _commands(cli_app, "skill")
    real = typer.main.get_command(cli_app)
    for group, titled in (
        ("mcp", False),
        ("agent", False),
        ("provider", True),
        ("channel", True),
        ("knowledge", False),
        ("memory", True),
    ):
        edit = real.commands[group].commands["edit"]  # type: ignore[attr-defined]
        assert ("--title" in {o for p in edit.params for o in p.opts}) is titled, group

    uid = _register("fake_kind", "alpha", {"foo": 1})
    by_name = _runner.invoke(app, ["fake", "disable", "alpha"])
    assert by_name.exit_code == 0, by_name.output
    assert _client().get(f"/resources/{uid}").json()["enabled"] is False
    assert _runner.invoke(app, ["fake", "enable", uid]).exit_code == 0
    by_uid = _runner.invoke(app, ["fake", "disable", uid])
    assert by_uid.exit_code == 0, by_uid.output
    assert _client().get(f"/resources/{uid}").json()["enabled"] is False
    assert len(_audit("resource_disabled")) == 2


def test_every_edit_offers_name_title_and_description() -> None:
    cmd = typer.main.get_command(_tree())
    fake_edit = cmd.commands["fake"].commands["edit"]  # type: ignore[attr-defined]
    scoped_edit = cmd.commands["scoped"].commands["edit"]  # type: ignore[attr-defined]
    assert {"--name", "--title", "--description", "--foo"} <= {
        o for p in fake_edit.params for o in p.opts
    }
    scoped = {o: p for p in scoped_edit.params for o in p.opts}
    assert {"--name", "--title", "--description"} <= set(scoped)
    assert "fixed" in (scoped["--name"].help or "")


def test_a_fixed_name_kind_reports_the_daemons_refusal(in_proc_daemon: Any) -> None:
    svc = _client().app.dependency_overrides[get_resource_service]()
    svc._kinds["fixed_kind"] = Kind(
        name="fixed_kind",
        display_name="Fixed",
        config_schema=_Lenient,
        name_fixed=True,
        name_fixed_resets="its reach",
    )
    uid = _register("fixed_kind", "search", {})
    root = typer.Typer()

    @root.callback()
    def _root(ctx: typer.Context) -> None:
        ctx.ensure_object(dict)

    group = typer.Typer()
    register_kind_verbs(group, KindVerbs(kind="fixed_kind", noun="fixed", name_fixed=True))
    root.add_typer(group, name="fixed")

    refused = _runner.invoke(root, ["fixed", "edit", "search", "--name", "other"])
    assert refused.exit_code == 5, refused.output
    assert "its reach" in refused.output
    assert _client().get(f"/resources/{uid}").json()["name"] == "search"


def test_list_show_and_edit_speak_the_kind_agnostic_routes(in_proc_daemon: Any) -> None:
    app = _tree()
    uid = _register("fake_kind", "alpha", {"foo": 1})

    edited = _runner.invoke(app, ["fake", "edit", "alpha", "--foo", "7", "--description", "d"])
    assert edited.exit_code == 0, edited.output
    row = _client().get(f"/resources/{uid}").json()
    assert row["config"]["foo"] == 7 and row["description"] == "d"

    renamed = _runner.invoke(app, ["fake", "edit", uid, "--name", "beta"])
    assert renamed.exit_code == 0, renamed.output
    assert _client().get(f"/resources/{uid}").json()["name"] == "beta"

    listed = _runner.invoke(app, ["fake", "list", "--json"])
    assert [r["name"] for r in json.loads(listed.output)["resources"]] == ["beta"]
    table = _runner.invoke(app, ["fake", "list"], env={"COLUMNS": "200"})
    assert "beta" in table.output and "7" in table.output

    shown = _runner.invoke(app, ["fake", "show", "beta", "--json"])
    assert json.loads(shown.output)["uid"] == uid
    assert _runner.invoke(app, ["fake", "show", "no-such"]).exit_code == 4
    assert _runner.invoke(app, ["fake", "edit", "beta"]).exit_code == 2


def test_rm_confirms_unless_told_not_to(in_proc_daemon: Any) -> None:
    app = _tree()
    uid = _register("fake_kind", "alpha", {"foo": 1})
    declined = _runner.invoke(app, ["fake", "rm", "alpha"], input="n\n")
    assert declined.exit_code == 1
    assert _client().get(f"/resources/{uid}").status_code == 200
    removed = _runner.invoke(app, ["fake", "rm", "alpha", "--yes"])
    assert removed.exit_code == 0, removed.output
    assert _client().get(f"/resources/{uid}").status_code == 404


def test_the_factory_generates_no_add() -> None:
    """Creation is a per-kind seam (spec resource-framework "Keep creation a
    per-kind seam"): asking the factory for ``add`` is a programming error."""
    assert "add" not in ALL_VERBS
    with pytest.raises(ValueError, match="add"):
        register_kind_verbs(
            typer.Typer(), KindVerbs(kind="fake_kind", noun="fake", verbs=frozenset({"add"}))
        )


@pytest.mark.acceptance(
    spec="resource-framework", scenario="the command line sets a resource's reach"
)
def test_scope_sets_reads_and_widens_reach(in_proc_daemon: Any) -> None:
    app = _tree()
    agent_uid = _agent("claude-code")
    uid = _register("fake_scoped", "search", {})

    narrowed = _runner.invoke(app, ["scoped", "scope", "search", "--agents", "claude-code"])
    assert narrowed.exit_code == 0, narrowed.output
    assert _client().get(f"/resources/{uid}/scope").json()["scope"] == {"agents": [agent_uid]}

    shown = _runner.invoke(app, ["scoped", "scope", "search"])
    assert shown.exit_code == 0 and "claude-code" in shown.output
    as_json = _runner.invoke(app, ["scoped", "scope", "search", "--json"])
    assert json.loads(as_json.output) == {"scope": {"agents": ["claude-code"]}}

    widened = _runner.invoke(app, ["scoped", "scope", "search", "--all"])
    assert widened.exit_code == 0 and "every agent" in widened.output
    assert _client().get(f"/resources/{uid}/scope").json()["scope"] is None

    dormant = _runner.invoke(app, ["scoped", "scope", "search", "--none"])
    assert dormant.exit_code == 0 and "dormant" in dormant.output
    assert len(_audit("resource_scope_updated")) == 3
    assert "scope" not in _commands(app, "fake")
    assert _runner.invoke(app, ["scoped", "scope", "search", "--all", "--none"]).exit_code == 2


def test_label_prefers_the_title_and_tolerates_its_absence() -> None:
    assert label({"name": "search", "title": "Team search"}) == "Team search"
    assert label({"name": "search", "title": None}) == "search"
    assert label({"name": "search"}) == "search"


def test_an_unknown_verb_is_a_programming_error() -> None:
    with pytest.raises(ValueError, match="unknown lifecycle verbs"):
        register_kind_verbs(typer.Typer(), KindVerbs(kind="k", noun="k", verbs=frozenset({"nuke"})))


def test_a_title_is_shown_where_the_name_was(in_proc_daemon: Any) -> None:
    app = _tree()
    uid = _register("fake_kind", "search", {"foo": 1})

    titled = _runner.invoke(app, ["fake", "edit", "search", "--title", "Team search"])
    assert titled.exit_code == 0, titled.output
    table = _runner.invoke(app, ["fake", "list"], env={"COLUMNS": "200"})
    assert "Team search" in table.output
    shown = _runner.invoke(app, ["fake", "show", "search"])
    assert shown.output.splitlines()[0] == "Team search"
    doc = json.loads(_runner.invoke(app, ["fake", "show", uid, "--json"]).output)
    assert (doc["name"], doc["title"]) == ("search", "Team search")

    cleared = _runner.invoke(app, ["fake", "edit", "search", "--title", ""])
    assert cleared.exit_code == 0, cleared.output
    assert _runner.invoke(app, ["fake", "show", "search"]).output.splitlines()[0] == "search"
