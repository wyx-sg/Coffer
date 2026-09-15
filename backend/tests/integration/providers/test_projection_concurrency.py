"""A projection never overwrites an edit the user made while it was deciding.

The projector reads an agent's native config, transforms it, and writes it
back. ``~/.claude/settings.json`` is the user's own file, open in their editor;
a save that lands between the read and the write used to be silently replaced
by Coffer's version. The store now carries the fingerprint of what was read and
refuses the write when the file no longer matches — a 409 ``CONFIG_FILE_STALE``
to the caller, an audit row from the service, and the user's edit intact.
"""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.provider.projection_ops import deproject_connection, project_connection
from coffer.application.provider.projector import ProviderProjector
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEntry, AuditEventType
from coffer.domain.provider.config import Protocol, ProviderConfig
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.workspace_errors import ConfigFileStale
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.surfaces.http.errors import _STATUS

_NOW = datetime(2026, 9, 14, tzinfo=UTC)


def _agent(config_dir: pathlib.Path) -> Resource:
    return Resource(
        id=1,
        kind="agent",
        name="cc",
        description=None,
        config={"type": "claude_code", "config_dir": str(config_dir)},
        enabled=True,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _connection() -> ProviderConfig:
    return ProviderConfig(
        protocol=Protocol.ANTHROPIC,
        base_url="https://gw.example",
        credential_ref="provider/x/key",
    )


class _EditedUnderneath(ConfigFileStore):
    """A store whose file is edited by the user right after every read —
    the race, made deterministic."""

    def __init__(self, edit: str) -> None:
        self._edit = edit
        self.reads = 0

    def read_text(self, path: pathlib.Path) -> str | None:
        text = super().read_text(path)
        self.reads += 1
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self._edit, encoding="utf-8")
        return text


@pytest.mark.acceptance(
    spec="provider-switching", scenario="projection refuses to overwrite a concurrent edit"
)
def test_projection_refuses_to_overwrite_a_concurrent_edit(tmp_path: pathlib.Path) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text('{"theme": "light"}', encoding="utf-8")
    store = _EditedUnderneath('{"theme": "dark"}')

    with pytest.raises(ConfigFileStale) as exc:
        ProviderProjector(store).project_type(
            "x", _connection(), [_agent(tmp_path)], AgentType.CLAUDE_CODE
        )

    assert exc.value.key == str(settings)
    assert settings.read_text(encoding="utf-8") == '{"theme": "dark"}', "the user's edit survives"
    assert _STATUS[ConfigFileStale.code] == 409


def test_deprojection_refuses_to_overwrite_a_concurrent_edit(tmp_path: pathlib.Path) -> None:
    settings = tmp_path / "settings.json"
    ProviderProjector(ConfigFileStore()).project_type(
        "x", _connection(), [_agent(tmp_path)], AgentType.CLAUDE_CODE
    )
    projected = settings.read_text(encoding="utf-8")
    store = _EditedUnderneath(projected.replace("}", ', "theme": "dark"}', 1))

    with pytest.raises(ConfigFileStale):
        ProviderProjector(store).deproject_type([_agent(tmp_path)], AgentType.CLAUDE_CODE)

    assert '"theme": "dark"' in settings.read_text(encoding="utf-8")


def test_unchanged_file_projects_normally_with_the_fingerprint_check(
    tmp_path: pathlib.Path,
) -> None:
    """The check is invisible when nobody edited the file: the projection lands."""
    settings = tmp_path / "settings.json"
    settings.write_text('{"theme": "light"}', encoding="utf-8")
    projected = ProviderProjector(ConfigFileStore()).project_type(
        "x", _connection(), [_agent(tmp_path)], AgentType.CLAUDE_CODE
    )
    assert projected == ["cc"]
    text = settings.read_text(encoding="utf-8")
    assert '"theme": "light"' in text and "gw.example" in text


class _FakeAudit:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def record(self, event_type: str, **kw: Any) -> None:
        self.entries.append({"event_type": event_type, **kw})


class _FakeService:
    """The three attributes ``projection_ops`` reaches into."""

    def __init__(self, store: ConfigFileStore) -> None:
        self._projector = ProviderProjector(store)
        self._audit = _FakeAudit()

    @staticmethod
    def _ref(name: str) -> ResourceRef:
        return ResourceRef("provider", name)


@pytest.mark.asyncio
async def test_service_audits_a_refused_projection_then_reraises(tmp_path: pathlib.Path) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text("{}", encoding="utf-8")
    service = _FakeService(_EditedUnderneath('{"theme": "dark"}'))

    with pytest.raises(ConfigFileStale):
        await project_connection(
            service,
            "x",
            _connection(),
            [AgentType.CLAUDE_CODE],
            [_agent(tmp_path)],
            actor="cli",  # type: ignore[arg-type]
        )

    (entry,) = service._audit.entries
    assert entry["event_type"] == AuditEventType.PROVIDER_PROJECTION_REFUSED.value
    assert entry["actor"] == "cli"
    assert entry["ref"] == ResourceRef("provider", "x")
    assert entry["details"]["path"] == str(settings)
    assert entry["details"]["agent_type"] == "claude_code"
    assert entry["details"]["connection"] == "x"


@pytest.mark.asyncio
async def test_service_audits_a_refused_deprojection(tmp_path: pathlib.Path) -> None:
    settings = tmp_path / "settings.json"
    ProviderProjector(ConfigFileStore()).project_type(
        "x", _connection(), [_agent(tmp_path)], AgentType.CLAUDE_CODE
    )
    edited = settings.read_text(encoding="utf-8").replace("}", ', "theme": "dark"}', 1)
    service = _FakeService(_EditedUnderneath(edited))

    with pytest.raises(ConfigFileStale):
        await deproject_connection(service, [_agent(tmp_path)], AgentType.CLAUDE_CODE, actor="api")  # type: ignore[arg-type]

    (entry,) = service._audit.entries
    assert entry["event_type"] == AuditEventType.PROVIDER_PROJECTION_REFUSED.value
    assert entry["ref"] is None and entry["details"]["connection"] is None


@pytest.mark.asyncio
async def test_successful_projection_audits_nothing_here(tmp_path: pathlib.Path) -> None:
    (tmp_path / "settings.json").write_text("{}", encoding="utf-8")
    service = _FakeService(ConfigFileStore())
    projected = await project_connection(
        service,
        "x",
        _connection(),
        [AgentType.CLAUDE_CODE],
        [_agent(tmp_path)],
        actor="cli",  # type: ignore[arg-type]
    )
    assert projected == ["cc"]
    assert service._audit.entries == []
    assert isinstance(AuditEntry, type)  # the audit row type is the one the log stores
