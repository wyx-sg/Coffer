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
from pydantic import BaseModel, ConfigDict

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


@pytest.mark.acceptance(spec="vault-sync", scenario="a resource document is identity, description and config")
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
    assert updated.config == {"colour": "pink", "path": ""} and updated.rev == b.rev + 1
    titled = await svc.set_title(a.uid, "Aye", actor="user")
    assert titled.title == "Aye"
    with pytest.raises(ResourceAlreadyExists):
        await svc.register("widget", "a", {"colour": "x"}, actor="user")
    await svc.delete(a.uid, actor="user")
    assert [r.name for r in await svc.list()] == ["b"]
    assert "resources/widget/a.json" not in _head_files()


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
@pytest.mark.acceptance(spec="vault-sync", scenario="a resource document is identity, description and config")
async def test_reach_is_local_and_never_committed() -> None:
    svc, _repo = _service(_kinds())
    r = await svc.register("widget", "w", {"colour": "blue"}, actor="user")
    head = vault_repository().head()
    off = await svc.set_enabled(r.uid, False, actor="user")
    assert off.enabled is False and off.rev == r.rev + 1
    assert vault_repository().head() == head
    reach = json.loads((local_root() / "reach.json").read_text())
    assert reach[r.uid] == {"enabled": False, "agents": None, "projects": None}
    assert not (vault_root() / "reach.json").exists()


async def test_unknown_fields_survive_a_write_at_the_top_and_inside_config() -> None:
    svc, _repo = _service(_kinds())
    r = await svc.register("widget", "w", {"colour": "blue"}, actor="user")
    path = _vault_file("resources/widget/w.json")
    raw = json.loads(path.read_text())
    raw["future_field"] = {"x": 1}
    raw["config"]["shade"] = "dark"
    path.write_text(json.dumps(raw, indent=2) + "\n")
    vault_writer().settle()
    seen = await svc.get(r.uid)
    assert "shade" not in seen.config
    await svc.update_config(r.uid, {"colour": "red"}, actor="user", description="changed")
    after = json.loads(path.read_text())
    assert after["future_field"] == {"x": 1}
    assert after["config"]["shade"] == "dark" and after["config"]["colour"] == "red"
    assert list(after) == list(raw)


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


@pytest.mark.acceptance(spec="vault-sync", scenario="machine-local files never reach the working tree")
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


@pytest.mark.acceptance(spec="vault-sync", scenario="a path under the home directory applies on a machine with a different home")
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


async def test_scope_is_reach_and_a_record_less_resource_gets_the_kind_default() -> None:
    kinds = _kinds()
    kinds["widget"] = Kind(
        name="widget",
        display_name="Widget",
        config_schema=WidgetConfig,
        supports_scope=True,
        default_scope=lambda _c: Scope(agents=["agent-1"]),
    )
    svc, _repo = _service(kinds)
    r = await svc.register("widget", "w", {"colour": "blue"}, actor="user")
    assert r.scope == Scope(agents=["agent-1"])
    (local_root() / "reach.json").unlink()
    again = await svc.get(r.uid)
    assert again.enabled is True and again.scope == Scope(agents=["agent-1"])


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
