from datetime import UTC, datetime

from coffer.domain.resource import Resource


def _now() -> datetime:
    return datetime.now(UTC)


def _resource(**overrides) -> Resource:
    fields = {
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


def test_there_is_no_surrogate_key():
    """The uid is the only identity: there is no integer row number beside it
    (ADR identity-is-the-uid-inside-the-file)."""
    r = _resource(uid="aaa", name="filesystem")
    assert not hasattr(r, "id")
    r.enabled = False
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
