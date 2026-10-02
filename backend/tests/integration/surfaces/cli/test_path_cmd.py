"""``coffer path`` names the plain files behind Coffer's state.

Every target is run against the real app in an isolated HOME, and each printed
path is checked to be absolute and to exist; a lookup that finds nothing
creates nothing.
"""

from __future__ import annotations

import json
import os
import pathlib
import textwrap
from collections.abc import Iterator
from typing import Any

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

from coffer.surfaces.cli.main import app as cli_app
from tests.integration.surfaces.cli.test_memory_cmd import _distilled_partition

from ._real_app import boot, extract_json

_runner = CliRunner()


@pytest.fixture
def daemon(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    (tmp_path / ".claude").mkdir()
    yield from boot(tmp_path, monkeypatch, features="knowledge=on,memory=on")


def _run(*args: str) -> Any:
    return _runner.invoke(cli_app, ["path", *args])


def _lines(output: str) -> list[str]:
    return [line for line in output.splitlines() if line.startswith("/")]


def _group_commands(group: str, command: str | None = None) -> set[str]:
    """A group's subcommand names, or one command's parameter names."""
    import typer.main

    node = typer.main.get_command(cli_app).commands[group]  # type: ignore[attr-defined]
    if command is None:
        return set(node.commands)
    return {p.name for p in node.commands[command].params}


def _tree(root: pathlib.Path) -> set[str]:
    return {str(p) for p in root.rglob("*")}


def _skill(home: pathlib.Path, name: str) -> None:
    folder = home / "src" / name
    folder.mkdir(parents=True)
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
    r = _runner.invoke(cli_app, ["skill", "add", str(folder)])
    assert r.exit_code == 0, r.output


@pytest.mark.acceptance(
    spec="resource-framework", scenario="the command line names the files behind a resource"
)
def test_the_command_line_names_the_files_behind_a_resource(
    daemon: TestClient, tmp_path: pathlib.Path
) -> None:
    assert daemon.post("/knowledge/collections", json={"name": "team"}).status_code == 201
    _skill(tmp_path, "lint-rules")

    collection = _run("knowledge", "team")
    assert collection.exit_code == 0, collection.output
    [directory] = _lines(collection.output)
    assert os.path.isabs(directory) and pathlib.Path(directory).is_dir()
    assert directory == str((tmp_path / ".coffer" / "vault" / "knowledge" / "team").resolve())

    skill = _run("skill", "lint-rules", "--json")
    assert skill.exit_code == 0, skill.output
    master = pathlib.Path(extract_json(skill.output)["skill"])
    assert master.is_absolute() and (master / "SKILL.md").is_file()

    before = _tree(tmp_path)
    missing = _run("skill", "no-such-skill")
    assert missing.exit_code == 4 and "no-such-skill" in missing.output
    assert _tree(tmp_path) == before


@pytest.mark.acceptance(
    spec="knowledge", scenario="locate a collection's documents from the command line"
)
def test_locate_a_collections_documents(daemon: TestClient, tmp_path: pathlib.Path) -> None:
    assert daemon.post("/knowledge/collections", json={"name": "shopee"}).status_code == 201
    doc = tmp_path / ".coffer" / "vault" / "knowledge" / "shopee" / "infra" / "cache.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("---\ntitle: Cache\ndescription: cache notes\n---\nbody\n", encoding="utf-8")

    [directory] = _lines(_run("knowledge", "shopee").output)
    assert (pathlib.Path(directory) / "infra" / "cache.md").read_text() == doc.read_text()
    [root] = _lines(_run("knowledge").output)
    assert root == str((tmp_path / ".coffer" / "vault" / "knowledge").resolve())
    assert _run("knowledge", "nope").exit_code == 4
    assert not {"collections", "create", "ls", "read", "save", "delete"} & _group_commands(
        "knowledge"
    )


@pytest.mark.acceptance(spec="memory", scenario="locate a partition's notes from the command line")
def test_locate_a_partitions_notes(daemon: TestClient, tmp_path: pathlib.Path) -> None:
    name = _distilled_partition(tmp_path)

    partition = _run("memory", name)
    assert partition.exit_code == 0, partition.output
    [directory] = _lines(partition.output)
    assert pathlib.Path(directory).is_dir()
    assert (pathlib.Path(directory) / "MEMORY.md").is_file()

    [root] = _lines(_run("memory").output)
    assert pathlib.Path(directory).parent == pathlib.Path(root)
    as_json = extract_json(_run("memory", name, "--json").output)
    assert as_json == {"memory": root, "partition": directory}
    removed = {"partitions", "notes", "note", "retired", "ls", "read", "distil"}
    removed |= {"delivery", "delivery-install", "delivery-remove", "context"}
    assert not removed & _group_commands("memory")


@pytest.mark.acceptance(
    spec="agent-registry", scenario="the command line names an agent's files by path"
)
def test_the_command_line_names_an_agents_files(daemon: TestClient, tmp_path: pathlib.Path) -> None:
    _distilled_partition(
        tmp_path
    )  # registers `claude-code` over ~/.claude with a memory store and a session
    (tmp_path / ".claude" / "CLAUDE.md").write_text("# me\n", encoding="utf-8")
    audited = len(daemon.get("/audit").json()["entries"])

    config = _run("agent", "claude-code", "config", "--json")
    assert config.exit_code == 0, config.output
    listed = [
        i["path"]
        for i in daemon.get(f"/agents/{_uid(daemon)}/config-files").json()["items"]
        if i["exists"]
    ]
    assert extract_json(config.output)["config"] == [str(pathlib.Path(p).resolve()) for p in listed]
    assert (
        str((tmp_path / ".claude" / "CLAUDE.md").resolve()) in extract_json(config.output)["config"]
    )

    memory = _lines(_run("agent", "claude-code", "memory").output)
    assert memory and all(pathlib.Path(p).is_dir() for p in memory)

    transcripts = _lines(_run("agent", "claude-code", "transcripts").output)
    assert transcripts and all(any(pathlib.Path(p).glob("*.jsonl")) for p in transcripts)

    assert len(daemon.get("/audit").json()["entries"]) == audited
    assert _run("agent", "claude-code", "plugins").exit_code == 2


def _uid(daemon: TestClient) -> str:
    return str(
        daemon.get("/resources", params={"kind": "agent", "name": "claude-code"}).json()[
            "resources"
        ][0]["uid"]
    )


@pytest.mark.acceptance(spec="daemon", scenario="the command line names the daemon log file")
def test_the_command_line_names_the_daemon_log_file(
    daemon: TestClient, tmp_path: pathlib.Path
) -> None:
    relocated = (tmp_path / "logs").resolve()
    log = relocated / "daemon.log"
    if not log.exists():  # the in-process app logs to the test's handlers, not a file
        relocated.mkdir(parents=True, exist_ok=True)
        log.write_text("{}\n", encoding="utf-8")

    plain = _run("logs")
    assert plain.exit_code == 0, plain.output
    assert _lines(plain.output) == [str(relocated), str(log)]
    as_json = extract_json(_run("logs", "--json").output)
    assert as_json == {"logs": str(relocated), "daemon_log": str(log)}
    assert pathlib.Path(as_json["daemon_log"]).is_file()


def test_path_with_no_target_prints_every_root(daemon: TestClient, tmp_path: pathlib.Path) -> None:
    body = extract_json(_run("--json").output)
    assert set(body) == {
        "vault",
        "knowledge",
        "memory",
        "skills",
        "home",
        "local",
        "content",
        "derived",
        "runs_db",
        "logs",
        "daemon_log",
    }
    coffer = (tmp_path / ".coffer").resolve()
    assert body["home"] == str(coffer)
    # The storage classes (ADR storage-is-five-classes-by-nature).
    assert body["vault"] == str(coffer / "vault")
    assert body["knowledge"] == str(coffer / "vault" / "knowledge")
    assert body["skills"] == str(coffer / "vault" / "skills")
    assert body["memory"] == str(coffer / "derived" / "memory")
    assert (body["local"], body["content"], body["derived"], body["runs_db"]) == (
        str(coffer / "local"),
        str(coffer / "content"),
        str(coffer / "derived"),
        str(coffer / "runs.db"),
    )
    assert all(os.path.isabs(v) for v in body.values())
    assert json.loads(json.dumps(body)) == body
    assert _lines(_run("vault").output) == [body["vault"]]


def test_a_switched_off_feature_names_its_switch(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for _client in boot(tmp_path, monkeypatch, features="knowledge=off,memory=off"):
        for target in ("knowledge", "memory"):
            r = _run(target)
            assert r.exit_code == 1
            assert f"coffer config set feature.{target} on" in r.output
