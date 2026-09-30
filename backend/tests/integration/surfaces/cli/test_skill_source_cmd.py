"""`coffer skill add <archive|git-url>` and `coffer skill update` (spec
skill-manager "Add skills from an archive", "Add skills from a Git
repository", "Update a Git-imported skill from its source").

The CLI is routed to an in-process daemon (the real ``create_app``) through
``_cli_client.client_or_exit``, as ``test_skill_cmd`` does; repositories are
bare ones under ``tmp_path`` over ``file://``.
"""

from __future__ import annotations

import json
import pathlib
import shutil
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.infrastructure.skill.master_store import default_master_root
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.skill_dependencies import get_skill_source_service
from tests.support.skill_sources import Upstream, make_upstream, skill_md, stage_dirs, zip_bytes

_runner = CliRunner()
_TOKEN = "test-token-skill-source-cli"


class _Persistent:
    """Keeps the CLI's ``with c:`` from closing the app's lifespan."""

    def __init__(self, inner: TestClient) -> None:
        self._inner = inner

    def __enter__(self) -> _Persistent:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def __getattr__(self, item: str) -> Any:
        return getattr(self._inner, item)


@pytest.fixture
def home(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[pathlib.Path]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59930")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59939")
    set_active_token(_TOKEN)
    info = DaemonInfo(
        version=1,
        pid=12345,
        port=59930,
        token=_TOKEN,
        started_at=datetime.now(tz=UTC),
        binary_path="/test",
    )
    client = TestClient(
        create_app(),
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "cli"},
        raise_server_exceptions=False,
    )
    client.__enter__()
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (_Persistent(client), info))
    yield tmp_path
    client.__exit__(None, None, None)
    set_active_token(None)


def _json(output: str) -> Any:
    lines = output.splitlines(keepends=True)
    start = next(i for i, ln in enumerate(lines) if ln[:1] in "[{")
    return json.loads("".join(lines[start:]))


def _user_skills() -> list[str]:
    r = _runner.invoke(cli_app, ["skill", "list", "--json"])
    assert r.exit_code == 0, r.output
    return sorted(i["name"] for i in _json(r.output) if i["name"] != "coffer-guide")


def _show(name: str) -> dict[str, Any]:
    r = _runner.invoke(cli_app, ["skill", "show", name, "--json"])
    assert r.exit_code == 0, r.output
    return _json(r.output)  # type: ignore[no-any-return]


def _two_skill_zip(home: pathlib.Path) -> pathlib.Path:
    path = home / "skills.zip"
    path.write_bytes(
        zip_bytes({"review/SKILL.md": skill_md("review"), "triage/SKILL.md": skill_md("triage")})
    )
    return path


@pytest.mark.acceptance(
    spec="skill-manager", scenario="an archive from the command line asks before adding"
)
def test_an_archive_asks_and_adds_only_on_yes(home: pathlib.Path) -> None:
    archive = _two_skill_zip(home)
    r = _runner.invoke(cli_app, ["skill", "add", str(archive), "--skill", "review"], input="n\n")
    assert r.exit_code == 0, r.output
    assert "found in skills.zip:" in r.output
    assert "review" in r.output and "triage" in r.output
    assert "add review?" in r.output and "nothing added" in r.output
    assert _user_skills() == []
    assert stage_dirs(get_skill_source_service()) == []

    r = _runner.invoke(cli_app, ["skill", "add", str(archive), "--skill", "review"], input="y\n")
    assert r.exit_code == 0, r.output
    assert "added: skill review" in r.output
    assert _user_skills() == ["review"]
    assert _show("review")["source"] == {
        "type": "archive_import",
        "archive_name": "skills.zip",
        "folder": "review",
    }
    assert stage_dirs(get_skill_source_service()) == []


def test_several_skills_need_a_choice_and_all_takes_every_one(home: pathlib.Path) -> None:
    archive = _two_skill_zip(home)
    r = _runner.invoke(cli_app, ["skill", "add", str(archive), "--yes"])
    assert r.exit_code == 6, r.output
    assert "--skill" in r.output
    r = _runner.invoke(cli_app, ["skill", "add", str(archive), "--skill", "nope", "--yes"])
    assert r.exit_code == 6 and "nope" in r.output
    assert stage_dirs(get_skill_source_service()) == []
    r = _runner.invoke(cli_app, ["skill", "add", str(archive), "--all", "--yes"])
    assert r.exit_code == 0, r.output
    assert _user_skills() == ["review", "triage"]


def test_a_taken_name_needs_force(home: pathlib.Path) -> None:
    archive = home / "one.zip"
    archive.write_bytes(zip_bytes({"SKILL.md": skill_md("review", "first")}))
    assert _runner.invoke(cli_app, ["skill", "add", str(archive), "--yes"]).exit_code == 0
    archive.write_bytes(zip_bytes({"SKILL.md": skill_md("review", "second")}))
    r = _runner.invoke(cli_app, ["skill", "add", str(archive), "--yes"])
    assert r.exit_code == 5 and "--force" in r.output
    assert "first" in (default_master_root() / "review" / "SKILL.md").read_text()
    r = _runner.invoke(cli_app, ["skill", "add", str(archive), "--yes", "--force"])
    assert r.exit_code == 0, r.output
    assert "second" in (default_master_root() / "review" / "SKILL.md").read_text()
    assert stage_dirs(get_skill_source_service()) == []


def test_ref_and_path_apply_to_a_repository_only(home: pathlib.Path) -> None:
    r = _runner.invoke(cli_app, ["skill", "add", str(_two_skill_zip(home)), "--ref", "main"])
    assert r.exit_code == 6 and "Git repository only" in r.output


@pytest.fixture
def up(home: pathlib.Path) -> Upstream:
    return make_upstream(
        home / "upstream",
        {"skills/review/SKILL.md": skill_md("review", "v1", requires='[jq, "gh>=2.40"]')},
        tag="v1.2",
    )


def test_a_repository_is_added_at_a_ref_and_path(home: pathlib.Path, up: Upstream) -> None:
    tagged = up.head()
    up.write("skills/review/SKILL.md", skill_md("review", "later"))
    up.commit("later")
    r = _runner.invoke(
        cli_app, ["skill", "add", up.url, "--ref", "v1.2", "--path", "skills/review", "--yes"]
    )
    assert r.exit_code == 0, r.output
    assert f"at {tagged[:7]}" in r.output and "added: skill review" in r.output
    data = _show("review")
    assert data["source"]["ref"] == "v1.2"
    assert data["source"]["subpath"] == "skills/review"
    assert data["source"]["commit"] == tagged
    assert data["requires"] == [
        {"command": "jq", "min_version": None},
        {"command": "gh", "min_version": "2.40"},
    ]
    assert "v1" in (default_master_root() / "review" / "SKILL.md").read_text()


def test_an_unreachable_repository_exits_non_zero(home: pathlib.Path) -> None:
    r = _runner.invoke(cli_app, ["skill", "add", f"file://{home}/nope.git", "--yes"])
    assert r.exit_code != 0
    assert "git clone failed" in r.output
    assert _user_skills() == []


def _move(up: Upstream) -> str:
    up.write("skills/review/SKILL.md", skill_md("review", "v2"))
    up.write("skills/review/extra.txt", "x\n")
    return up.commit("v2 change")


def _add_git(up: Upstream) -> None:
    r = _runner.invoke(cli_app, ["skill", "add", up.url, "--path", "skills/review", "--yes"])
    assert r.exit_code == 0, r.output


@pytest.mark.acceptance(spec="skill-manager", scenario="update a skill from the command line")
def test_update_previews_asks_and_applies(home: pathlib.Path, up: Upstream) -> None:
    _add_git(up)
    first = _show("review")["source"]["commit"]
    r = _runner.invoke(cli_app, ["skill", "update", "review", "--check"])
    assert r.exit_code == 0 and "up to date" in r.output
    new = _move(up)

    r = _runner.invoke(cli_app, ["skill", "update", "review", "--check"])
    assert r.exit_code == 0, r.output
    assert f"update available: 1 commit(s), 2 file(s), up to {new[:7]}" in r.output
    r = _runner.invoke(cli_app, ["skill", "update", "review", "--check", "--json"])
    status = _json(r.output)
    assert (status["update_available"], status["latest_commit"]) == (True, new)

    r = _runner.invoke(cli_app, ["skill", "update", "review"], input="n\n")
    assert r.exit_code == 0, r.output
    assert f"{first[:7]}..{new[:7]}" in r.output
    assert "+ extra.txt" in r.output and "~ SKILL.md" in r.output
    assert "nothing changed" in r.output
    assert _show("review")["source"]["commit"] == first
    assert stage_dirs(get_skill_source_service()) == []

    r = _runner.invoke(cli_app, ["skill", "update", "review"], input="y\n")
    assert r.exit_code == 0, r.output
    assert f"updated: skill review to {new[:7]}" in r.output
    assert _show("review")["source"]["commit"] == new
    assert "v2" in (default_master_root() / "review" / "SKILL.md").read_text()
    r = _runner.invoke(cli_app, ["skill", "update", "review", "--yes"])
    assert r.exit_code == 0 and "up to date" in r.output


@pytest.mark.acceptance(spec="skill-manager", scenario="update a skill from the command line")
def test_update_refuses_a_conflict_until_a_side_is_named(home: pathlib.Path, up: Upstream) -> None:
    _add_git(up)
    first = _show("review")["source"]["commit"]
    skill_file = default_master_root() / "review" / "SKILL.md"
    skill_file.write_text(skill_md("review", "mine"))
    new = _move(up)

    r = _runner.invoke(cli_app, ["skill", "update", "review", "--yes"])
    assert r.exit_code == 5, r.output
    assert "your edits since the pin:" in r.output and "--take-theirs" in r.output
    assert "mine" in skill_file.read_text()

    r = _runner.invoke(cli_app, ["skill", "update", "review", "--keep-mine"])
    assert r.exit_code == 0, r.output
    assert f"{new[:7]} will not be offered again" in r.output
    assert _show("review")["source"]["commit"] == first
    assert "mine" in skill_file.read_text()
    r = _runner.invoke(cli_app, ["skill", "update", "review", "--check", "--json"])
    assert _json(r.output)["update_available"] is False

    r = _runner.invoke(cli_app, ["skill", "update", "review", "--take-theirs", "--yes"])
    assert r.exit_code == 0, r.output
    assert _show("review")["source"]["commit"] == new
    assert "mine" not in skill_file.read_text()
    assert stage_dirs(get_skill_source_service()) == []


def test_update_refuses_both_sides_and_an_unreachable_check_fails(
    home: pathlib.Path, up: Upstream
) -> None:
    _add_git(up)
    r = _runner.invoke(cli_app, ["skill", "update", "review", "--take-theirs", "--keep-mine"])
    assert r.exit_code == 6
    shutil.rmtree(up.bare)
    r = _runner.invoke(cli_app, ["skill", "update", "review", "--check"])
    assert r.exit_code == 1
    assert "source unreachable: git clone failed" in r.output
