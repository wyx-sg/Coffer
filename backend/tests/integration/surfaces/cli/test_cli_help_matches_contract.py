"""Help text that tells a person how to call a command must name what the daemon
accepts: the archive formats of ``skill stage-archive``, the agent keys of
``agent session all --agent``, and the bodies of the MCP exposure and capability
toggle commands."""

from __future__ import annotations

import io
import json
import pathlib
import re
import tarfile
from collections.abc import Iterator
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from coffer.application.agent.native_session_service import SourcePage
from coffer.domain.agent.native_sessions import NativeSession
from coffer.domain.agent.types import AgentType
from coffer.surfaces.cli.main import app
from coffer.surfaces.http import workspace_dependencies
from coffer.surfaces.http.mcp.page_schemas import ToolExposureBatchBody, ToolExposureBody
from coffer.surfaces.http.schemas import CapabilityKeyBody
from tests.support.skill_sources import skill_md, zip_bytes

from ._real_app import boot, extract_json

_runner = CliRunner()


def _command(path: list[str]) -> Any:
    cmd: Any = typer.main.get_command(app)
    for name in path:
        cmd = cmd.commands[name]
    return cmd


def _help_of(path: list[str]) -> str:
    cmd = _command(path)
    return "\n".join([cmd.help or "", *(p.help for p in cmd.params if getattr(p, "help", None))])


@pytest.fixture
def client(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    yield from boot(tmp_path, monkeypatch)


def test_stage_archive_help_names_only_the_supported_formats() -> None:
    text = _help_of(["skill", "stage-archive"])
    assert ".zip" in text and ".skill" in text
    assert "tar" not in text.lower()


def test_a_tar_gz_is_refused_and_a_zip_stages(client: Any, tmp_path: pathlib.Path) -> None:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        data = skill_md("tarred").encode() if isinstance(skill_md("tarred"), str) else b""
        info = tarfile.TarInfo("tarred/SKILL.md")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    tarball = tmp_path / "x.tar.gz"
    tarball.write_bytes(buf.getvalue())
    refused = _runner.invoke(app, ["skill", "stage-archive", str(tarball), "--json"])
    assert refused.exit_code == 6, refused.output

    archive = tmp_path / "x.zip"
    archive.write_bytes(zip_bytes({"zipped/SKILL.md": skill_md("zipped")}))
    staged = _runner.invoke(app, ["skill", "stage-archive", str(archive), "--json"])
    assert staged.exit_code == 0, staged.output
    assert "zipped" in json.dumps(extract_json(staged.output))


def test_agent_session_all_help_says_keys_not_uid() -> None:
    cmd = _command(["agent", "session", "all"])
    agent = next(p for p in cmd.params if p.name == "agent")
    assert "key" in agent.help.lower() and "uid" not in agent.help.lower()


class _Source:
    def __init__(self, rows: list[NativeSession]) -> None:
        self.rows = rows

    async def list(
        self, config_dir: pathlib.Path, *, q: str | None, limit: int, position: list[Any] | None
    ) -> SourcePage:
        return SourcePage(self.rows, None, None)


def test_agent_session_all_filters_by_the_key_the_help_names(
    client: Any, tmp_path: pathlib.Path
) -> None:
    from datetime import UTC, datetime

    for agent_type in ("claude_code", "codex"):
        config_dir = tmp_path / f".{agent_type}"
        config_dir.mkdir()
        r = client.post(
            "/agents", json={"type": agent_type, "name": agent_type, "config_dir": str(config_dir)}
        )
        assert r.status_code == 201, r.text
    at = datetime(2026, 9, 1, 10, tzinfo=UTC)
    service = workspace_dependencies.get_native_session_service()
    service._sources[AgentType.CLAUDE_CODE] = _Source([NativeSession("c1", "c", "/w", at, at)])  # type: ignore[index]
    service._sources[AgentType.CODEX] = _Source([NativeSession("x1", "x", "/w", at, at)])  # type: ignore[index]

    out = _runner.invoke(app, ["agent", "session", "all", "--agent", "codex", "--json"])
    assert out.exit_code == 0, out.output
    assert [s["session_id"] for s in extract_json(out.output)["sessions"]] == ["x1"]


_JSON_EXAMPLE = re.compile(r'(\{"[^{}]*(?:\[[^\]]*\][^{}]*)*\})')


def _examples(path: list[str]) -> list[Any]:
    return [json.loads(m) for m in _JSON_EXAMPLE.findall(_help_of(path))]


def test_mcp_exposure_examples_validate_against_the_body_models() -> None:
    one = _examples(["mcp", "exposure"])
    many = _examples(["mcp", "exposure-all"])
    assert one and many
    for example in one:
        ToolExposureBody.model_validate(example)
    for example in many:
        ToolExposureBatchBody.model_validate(example)
    assert "always" not in _help_of(["mcp", "exposure"])


@pytest.mark.parametrize("verb", ["enable", "disable"])
def test_mcp_capability_toggle_examples_validate(verb: str) -> None:
    examples = _examples(["mcp", "tool", verb])
    assert examples
    for example in examples:
        CapabilityKeyBody.model_validate(example)
