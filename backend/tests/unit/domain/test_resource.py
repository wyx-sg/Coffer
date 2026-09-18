from datetime import UTC, datetime

from coffer.domain.resource import Resource


def _now() -> datetime:
    return datetime.now(UTC)


def _resource(**overrides) -> Resource:
    fields = {
        "id": 1,
        "uid": "9f2c1a7b4e8d4c1fa0b3d5e6f7081920",
        "kind": "mcp_server",
        "name": "filesystem",
        "description": None,
        "config": {},
        "enabled": True,
        "created_at": _now(),
        "updated_at": _now(),
    }
    fields.update(overrides)
    return Resource(**fields)  # type: ignore[arg-type]


def test_identity_is_the_uid_and_the_name_is_a_separate_label():
    """Replaces the old ``r.ref == ResourceRef(kind, name)`` assertion.

    That test pinned the claim that a resource's identity was DERIVABLE from
    its label — which is precisely what the identity change removed. The
    assertion that carries the same meaning now is that the two are separate
    fields, that the identity is the uid, and that nothing reconstructs one
    from the other: there is no ``ref`` to compute.
    """
    r = _resource()
    assert r.uid == "9f2c1a7b4e8d4c1fa0b3d5e6f7081920"
    assert r.name == "filesystem"
    assert not hasattr(r, "ref")


def test_the_surrogate_key_is_not_the_identity():
    """``id`` is a row number — per-machine, internal — and ``uid`` is the
    identity, which is why two resources may share neither but are told apart
    by the uid alone."""
    a = _resource(id=1, uid="aaa", name="filesystem")
    b = _resource(id=1, uid="bbb", name="filesystem")
    assert a.id == b.id
    assert a.uid != b.uid


def test_resource_is_mutable_dataclass():
    """Resource is a regular dataclass — repos may mutate id/updated_at."""
    r = _resource(id=0, name="x")
    r.id = 42
    r.enabled = False
    assert r.id == 42
    assert r.enabled is False


def test_the_label_may_move_while_the_identity_does_not():
    """A rename writes ``name``; ``uid`` is immutable by contract, and every
    reference elsewhere in the vault holds the uid precisely so that a label
    edit costs nothing."""
    r = _resource(name="before")
    uid_before = r.uid
    r.name = "after"
    assert r.name == "after"
    assert r.uid == uid_before
