"""Resources as files (coffer.infrastructure.vault.resource_store; spec
vault-storage "Identify a resource by the uid inside its file", "Keep every
vault document a JSON object that preserves what it does not know", "Store
state in five classes by nature", "Keep the last valid version when a hand
edit is invalid")."""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict, field_validator

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.domain.errors import ResourceAlreadyExists
from coffer.domain.resource import Kind, Resource
from coffer.domain.scope import Scope
from coffer.domain.vault.errors import VaultFileStale
from coffer.domain.vault.findings import FindingCode
from coffer.domain.vault.layout import StorageClass
from coffer.domain.vault.writers import WRITER_DAEMON, WRITER_DISK, WRITER_USER
from coffer.infrastructure.vault.home import derived_root, local_root, vault_root
from coffer.infrastructure.vault.instance import vault_repository, vault_writer
from tests.support.vault_stores import make_resource_repo


class WidgetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    colour: str
    path: str = ""


def _kinds() -> dict[str, Kind]:
    return {
        "widget": Kind(name="widget", display_name="Widget", config_schema=WidgetConfig),
        "gadget": Kind(
            name="gadget",
            display_name="Gadget",
            config_schema=WidgetConfig,
            storage=StorageClass.LOCAL,
            generic_create_allowed=True,
        ),
        "gizmo": Kind(
            name="gizmo",
            display_name="Gizmo",
            config_schema=WidgetConfig,
            storage=StorageClass.DERIVED,
        ),
    }


class _Dirs(BaseModel):
    """A config whose paths must be absolute, as the kind reads them."""

    model_config = ConfigDict(extra="forbid")
    directories: list[str] = []
    default: str | None = None

    @field_validator("directories")
    @classmethod
    def _absolute(cls, v: list[str]) -> list[str]:
        if not all(Path(d).is_absolute() for d in v):
            raise ValueError("directories must be absolute")
        return v


class _NullAudit:
    async def insert(self, entry: object) -> None:
        return None

    async def query(self, **_: object) -> list[object]:
        return []

    async def count(self, **_: object) -> int:
        return 0


def _service(kinds: dict[str, Kind]) -> tuple[ResourceService, object]:
    repo = make_resource_repo(kinds)
    return ResourceService(kinds=kinds, repo=repo, audit=AuditService(_NullAudit())), repo


def _resource(kind: str, name: str, config: dict[str, object]) -> Resource:
    now = datetime.now(tz=UTC)
    return Resource(
        uid=uuid.uuid4().hex,
        kind=kind,
        name=name,
        description=None,
        config=config,
        enabled=True,
        created_at=now,
        updated_at=now,
    )


def _head_files(prefix: str = "resources/") -> dict[str, str]:
    return vault_repository().tree("HEAD", prefix)


def _vault_file(path: str) -> Path:
    return vault_root() / path


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a resource document is identity, description and config"
)
async def test_a_resource_is_a_file_named_after_it_with_its_uid_inside() -> None:
    svc, _repo = _service(_kinds())
    created = await svc.register("widget", "blue", {"colour": "blue"}, actor="user")
    assert list(_head_files()) == ["resources/widget/blue.json"]
    doc = json.loads(_vault_file("resources/widget/blue.json").read_text())
    assert doc["uid"] == created.uid and doc["kind"] == "widget" and doc["format_version"] == 1
    assert "enabled" not in doc and "scope" not in doc and "rev" not in doc
    commit = vault_repository().log(limit=1)[0]
    assert commit.meta.writer == WRITER_USER and commit.meta.actor == "user"
    assert await svc.get(created.uid) == created
    assert (await svc.get_by_name("widget", "blue")).uid == created.uid


async def test_crud_round_trip_and_ordering() -> None:
    svc, _repo = _service(_kinds())
    b = await svc.register("widget", "b", {"colour": "red"}, actor="user", description="bee")
    a = await svc.register("widget", "a", {"colour": "green"}, actor="user")
    assert [r.name for r in await svc.list(kind="widget")] == ["a", "b"]
    updated = await svc.update_config(b.uid, {"colour": "pink"}, actor="user", description="bee")
    assert updated.config == {"colour": "pink", "path": ""}
    with pytest.raises(ResourceAlreadyExists):
        await svc.register("widget", "a", {"colour": "x"}, actor="user")
    await svc.delete(a.uid, actor="user")
    assert [r.name for r in await svc.list()] == ["b"]
    assert "resources/widget/a.json" not in _head_files()


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a rename moves the resource's file in one commit"
)
async def test_rename_moves_the_file_in_one_commit() -> None:
    svc, _repo = _service(_kinds())
    r = await svc.register("widget", "old", {"colour": "blue"}, actor="user")
    before = vault_repository().head()
    renamed = await svc.rename(r.uid, "new", actor="user")
    assert renamed.uid == r.uid and renamed.name == "new"
    commits = vault_repository().log(start=vault_repository().head(), limit=5)
    assert commits[1].version == before
    assert sorted(p.path for p in commits[0].paths) == [
        "resources/widget/new.json",
        "resources/widget/old.json",
    ]
    assert list(_head_files()) == ["resources/widget/new.json"]


@pytest.mark.acceptance(spec="vault-sync", scenario="reach stays on the machine it was set on")
@pytest.mark.acceptance(
    spec="vault-sync", scenario="a resource document is identity, description and config"
)
@pytest.mark.acceptance(
    spec="resource-framework", scenario="reach is kept on this machine, not in the resource's file"
)
async def test_reach_is_local_and_never_committed() -> None:
    svc, _repo = _service(_kinds())
    r = await svc.register("widget", "w", {"colour": "blue"}, actor="user")
    head = vault_repository().head()
    off = await svc.set_enabled(r.uid, False, actor="user")
    assert off.enabled is False
    assert vault_repository().head() == head
    reach = json.loads((local_root() / "reach.json").read_text())
    assert reach[r.uid] == {"enabled": False, "agents": None, "projects": None}
    assert not (vault_root() / "reach.json").exists()


@pytest.mark.acceptance(
    spec="vault-storage", scenario="a field this build does not know survives a write"
)
async def test_an_unknown_top_level_field_survives_a_write() -> None:
    svc, _repo = _service(_kinds())
    r = await svc.register("widget", "w", {"colour": "blue"}, actor="user")
    path = _vault_file("resources/widget/w.json")
    raw = json.loads(path.read_text())
    raw["future_field"] = {"x": 1}
    path.write_text(json.dumps(raw, indent=2) + "\n")
    vault_writer().settle()
    assert "resources/widget/w.json" not in vault_writer().problems()
    await svc.update_config(r.uid, {"colour": "red"}, actor="user", description="changed")
    after = json.loads(path.read_text())
    assert after["future_field"] == {"x": 1}
    assert after["config"]["colour"] == "red" and "shade" not in after["config"]
    assert list(after) == list(raw)


@pytest.mark.acceptance(
    spec="vault-storage", scenario="a config key the kind does not declare is refused"
)
async def test_a_config_key_the_kind_does_not_declare_is_refused() -> None:
    svc, _repo = _service(_kinds())
    r = await svc.register("widget", "w", {"colour": "blue"}, actor="user")
    path = _vault_file("resources/widget/w.json")
    committed = path.read_bytes()
    raw = json.loads(committed)
    raw["config"]["shade"] = "dark"
    path.write_text(json.dumps(raw, indent=2) + "\n")
    vault_writer().settle()
    [finding] = vault_writer().problems()["resources/widget/w.json"]
    assert finding.code is FindingCode.CONFIG_INVALID and "'shade'" in finding.message
    assert vault_repository().read("HEAD", "resources/widget/w.json") == committed
    assert (await svc.get(r.uid)).config["colour"] == "blue"
    assert "shade" not in (await svc.get(r.uid)).config


@pytest.mark.acceptance(
    spec="vault-storage", scenario="a copied resource file is flagged and the original is untouched"
)
async def test_a_copied_file_is_flagged_duplicate_and_the_original_is_unchanged() -> None:
    svc, _repo = _service(_kinds())
    r = await svc.register("widget", "w", {"colour": "blue"}, actor="user")
    original = _vault_file("resources/widget/w.json").read_bytes()
    copy = _vault_file("resources/widget/w-copy.json")
    doc = json.loads(original)
    doc["name"] = "w-copy"
    copy.write_text(json.dumps(doc, indent=2) + "\n")
    vault_writer().settle()
    problems = vault_writer().problems()
    assert [f.code for f in problems["resources/widget/w-copy.json"]] == [FindingCode.DUPLICATE_UID]
    assert "resources/widget/w-copy.json" not in _head_files()
    assert (await svc.get(r.uid)).name == "w"
    assert _vault_file("resources/widget/w.json").read_bytes() == original


@pytest.mark.acceptance(spec="vault-storage", scenario="a hand-made resource file is given a uid")
async def test_a_hand_made_file_without_a_uid_is_given_one_by_a_daemon_commit() -> None:
    svc, _repo = _service(_kinds())
    vault_repository().ensure()
    path = _vault_file("resources/widget/hand.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"kind": "widget", "name": "hand", "config": {"colour": "x"}}))
    vault_writer().settle()
    first, second = vault_repository().log(limit=2)
    assert second.meta.writer == WRITER_DISK
    assert first.meta.writer == WRITER_DAEMON and first.meta.operation == "mint-uid"
    uid = json.loads(path.read_text())["uid"]
    found = await svc.get(uid)
    assert found.name == "hand" and found.config["colour"] == "x"


async def test_an_invalid_hand_edit_leaves_the_last_valid_config_in_effect() -> None:
    svc, _repo = _service(_kinds())
    r = await svc.register("widget", "w", {"colour": "blue"}, actor="user")
    path = _vault_file("resources/widget/w.json")
    path.write_text("{ not json")
    vault_writer().settle()
    assert FindingCode.INVALID_DOCUMENT in [
        f.code for f in vault_writer().problems()["resources/widget/w.json"]
    ]
    assert (await svc.get(r.uid)).config["colour"] == "blue"
    # A daemon write over the unsettled edit is refused, never a silent overwrite.
    with pytest.raises(VaultFileStale):
        await svc.update_config(r.uid, {"colour": "red"}, actor="user")
    assert path.read_text() == "{ not json"


async def test_a_config_the_schema_refuses_stays_out_of_head() -> None:
    svc, _repo = _service(_kinds())
    r = await svc.register("widget", "w", {"colour": "blue"}, actor="user")
    path = _vault_file("resources/widget/w.json")
    doc = json.loads(path.read_text())
    doc["config"]["colour"] = 42
    path.write_text(json.dumps(doc, indent=2) + "\n")
    vault_writer().settle()
    codes = [f.code for f in vault_writer().problems()["resources/widget/w.json"]]
    assert codes == [FindingCode.CONFIG_INVALID]
    assert (await svc.get(r.uid)).config["colour"] == "blue"


@pytest.mark.acceptance(
    spec="vault-sync", scenario="machine-local files never reach the working tree"
)
@pytest.mark.acceptance(spec="vault-storage", scenario="each class has its own directory")
async def test_local_and_derived_kinds_are_filed_outside_git() -> None:
    svc, _repo = _service(_kinds())
    g = await svc.register("gadget", "g", {"colour": "blue"}, actor="user")
    z = await svc.register("gizmo", "z", {"colour": "blue"}, actor="user")
    assert (local_root() / "resources" / "gadget" / "g.json").is_file()
    assert (derived_root() / "resources" / "gizmo" / "z.json").is_file()
    assert _head_files() == {}
    assert {r.uid for r in await svc.list()} == {g.uid, z.uid}
    renamed = await svc.rename(g.uid, "g2", actor="user")
    assert renamed.name == "g2"
    assert (local_root() / "resources" / "gadget" / "g2.json").is_file()
    assert not (local_root() / "resources" / "gadget" / "g.json").exists()
    await svc.delete(z.uid, actor="user")
    assert not (derived_root() / "resources" / "gizmo" / "z.json").exists()


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="a path under the home directory applies on a machine with a different home",
)
async def test_a_path_under_home_is_written_portably_and_read_back_expanded() -> None:
    svc, _repo = _service(_kinds())
    home = os.environ["HOME"]
    r = await svc.register("widget", "w", {"colour": "b", "path": f"{home}/x"}, actor="user")
    doc = json.loads(_vault_file("resources/widget/w.json").read_text())
    assert doc["config"]["path"] == "${HOME}/x"
    assert (await svc.get(r.uid)).config["path"] == f"{home}/x"


async def test_a_name_clash_with_an_unrelated_file_falls_back_to_the_uid() -> None:
    kinds = _kinds()
    _svc, repo = _service(kinds)
    stray = _vault_file("resources/widget/w.json")
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_text("unrelated\n")
    r = _resource("widget", "w", {"colour": "b"})
    await repo.create(r)  # type: ignore[attr-defined]
    assert f"resources/widget/w-{r.uid[:8]}.json" in _head_files()
    assert stray.read_text() == "unrelated\n"


@pytest.mark.acceptance(
    spec="resource-framework", scenario="reach is kept on this machine, not in the resource's file"
)
async def test_scope_is_reach_and_a_record_less_resource_reads_as_on_for_every_agent() -> None:
    kinds = _kinds()
    kinds["widget"] = Kind(
        name="widget",
        display_name="Widget",
        config_schema=WidgetConfig,
        supports_scope=True,
    )
    svc, _repo = _service(kinds)
    r = await svc.register("widget", "w", {"colour": "blue"}, actor="user")
    assert r.scope is None
    scoped = await svc.update_scope(r.uid, Scope(agents=["agent-1"]), actor="user")
    assert scoped.scope == Scope(agents=["agent-1"])
    (local_root() / "reach.json").unlink()
    again = await svc.get(r.uid)
    assert again.enabled is True and again.scope is None


@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="a reach record left with no agent is switched off at startup",
)
async def test_a_record_left_with_no_agent_is_switched_off_by_the_startup_step() -> None:
    from coffer.infrastructure.vault.reach_store import ReachStore

    svc, _repo = _service(_kinds())
    on = await svc.register("widget", "on", {"colour": "blue"}, actor="user")
    empty_on = await svc.register("widget", "empty-on", {"colour": "blue"}, actor="user")
    empty_off = await svc.register("widget", "empty-off", {"colour": "blue"}, actor="user")
    chosen = await svc.register("widget", "chosen", {"colour": "blue"}, actor="user")
    (local_root() / "reach.json").write_text(
        json.dumps(
            {
                on.uid: {"enabled": True, "agents": None, "projects": None},
                empty_on.uid: {"enabled": True, "agents": [], "projects": None},
                empty_off.uid: {"enabled": False, "agents": [], "projects": None},
                chosen.uid: {"enabled": True, "agents": ["agent-1"], "projects": None},
            }
        ),
        encoding="utf-8",
    )

    assert ReachStore().switch_off_empty_scopes() == 2
    # Idempotent: a second run finds nothing left to rewrite.
    assert ReachStore().switch_off_empty_scopes() == 0

    for uid in (empty_on.uid, empty_off.uid):
        got = await svc.get(uid)
        assert got.enabled is False and got.scope is None
    assert (await svc.get(on.uid)).enabled is True
    kept = await svc.get(chosen.uid)
    assert kept.enabled is True and kept.scope == Scope(agents=["agent-1"])


async def test_a_stale_off_record_for_a_kind_with_no_switch_reads_as_on() -> None:
    kinds = _kinds()
    kinds["widget"] = Kind(
        name="widget", display_name="Widget", config_schema=WidgetConfig, toggleable=False
    )
    svc, _repo = _service(kinds)
    r = await svc.register("widget", "w", {"colour": "blue"}, actor="user")
    reach_file = local_root() / "reach.json"
    reach_file.write_text(
        json.dumps({r.uid: {"enabled": False, "agents": None, "projects": None}}),
        encoding="utf-8",
    )
    assert (await svc.get(r.uid)).enabled is True
    assert [x.uid for x in await svc.list(kind="widget", enabled=True)] == [r.uid]


@pytest.mark.acceptance(spec="vault-storage", scenario="moving a resource file keeps the resource")
async def test_a_file_moved_by_hand_is_the_same_resource_with_its_reach() -> None:
    svc, _repo = _service(_kinds())
    r = await svc.register("widget", "w", {"colour": "blue"}, actor="user")
    await svc.set_enabled(r.uid, False, actor="user")
    os.rename(_vault_file("resources/widget/w.json"), _vault_file("resources/widget/moved.json"))
    vault_writer().settle()
    assert "resources/widget/moved.json" in _head_files()
    assert "resources/widget/w.json" not in _head_files()
    found = await svc.get(r.uid)
    assert found.name == "w" and found.enabled is False
    assert found.config["colour"] == "blue"


@pytest.mark.acceptance(spec="vault-storage", scenario="deleting derived state loses nothing")
async def test_deleting_derived_loses_no_resource() -> None:
    import shutil

    from coffer.infrastructure.persistence.derived_db import derived_db_path, open_derived_db

    kinds = _kinds()
    svc, _repo = _service(kinds)
    kept = await svc.register("widget", "w", {"colour": "blue"}, actor="user")
    engine, _sm = await open_derived_db()
    await engine.dispose()
    assert derived_db_path().exists()
    shutil.rmtree(derived_root())
    again, _repo2 = _service(kinds)
    found = await again.get(kept.uid)
    assert found.name == "w" and found.config["colour"] == "blue"
    engine, _sm = await open_derived_db()
    await engine.dispose()
    assert derived_db_path().exists()


@pytest.mark.acceptance(
    spec="vault-sync", scenario="an absolute path under the home directory passes validation"
)
@pytest.mark.parametrize("change", ["add", "remove", "set default"])
async def test_a_directory_under_home_is_written_and_removed(change: str) -> None:
    """Directories under HOME are filed as ``${HOME}/...``; the vault validator
    judges the config as the kind reads it, so adding, removing or defaulting
    one is not refused for not being an absolute path."""
    kinds = {"workspace": Kind(name="workspace", display_name="W", config_schema=_Dirs)}
    repo = make_resource_repo(kinds)
    home = os.environ["HOME"]
    first, second = f"{home}/WorkEnv/account", f"{home}/WorkEnv/account-bff"
    config: dict[str, object] = {"directories": [first]}
    created = await repo.create(_resource("workspace", "ws", config))
    after = {
        "add": {**config, "directories": [first, second]},
        "remove": {**config, "directories": []},
        "set default": {**config, "default": first},
    }[change]

    updated = await repo.update_config(created.uid, after, None)

    assert updated.config["directories"] == after["directories"]
    doc = json.loads(_vault_file("resources/workspace/ws.json").read_text())
    stored = [
        *doc["config"]["directories"],
        *([doc["config"]["default"]] if change == "set default" else []),
    ]
    assert all(d.startswith("${HOME}/") for d in stored)
    assert "resources/workspace/ws.json" in _head_files()
