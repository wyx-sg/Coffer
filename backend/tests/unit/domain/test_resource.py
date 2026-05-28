from datetime import UTC, datetime

from coffer.domain.resource import Resource, ResourceRef


def _now() -> datetime:
    return datetime.now(UTC)


def test_resource_ref_property():
    r = Resource(
        id=1,
        kind="mcp_server",
        name="filesystem",
        description=None,
        config={},
        enabled=True,
        created_at=_now(),
        updated_at=_now(),
    )
    assert r.ref == ResourceRef("mcp_server", "filesystem")


def test_resource_is_mutable_dataclass():
    """Resource is a regular dataclass — repos may mutate id/updated_at."""
    r = Resource(
        id=0,
        kind="mcp_server",
        name="x",
        description=None,
        config={},
        enabled=True,
        created_at=_now(),
        updated_at=_now(),
    )
    r.id = 42
    r.enabled = False
    assert r.id == 42
    assert r.enabled is False
