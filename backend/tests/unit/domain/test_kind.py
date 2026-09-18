from datetime import UTC, datetime

from pydantic import BaseModel

from coffer.domain.resource import Kind, Resource


class _FooConfig(BaseModel):
    x: int


def _resource(name: str = "bar") -> Resource:
    now = datetime.now(tz=UTC)
    return Resource(
        id=1,
        uid="f00d1e55",
        kind="foo",
        name=name,
        description=None,
        config={},
        enabled=True,
        created_at=now,
        updated_at=now,
    )


def test_kind_basic():
    k = Kind(name="foo", display_name="Foo", config_schema=_FooConfig)
    assert k.name == "foo"
    assert k.config_schema is _FooConfig
    assert k.on_delete is None
    # A kind that keeps no directory named after the resource supplies no
    # rename hook either — renaming it is one column and nothing else.
    assert k.on_rename is None


def test_kind_on_delete_hook():
    """The hook is handed the RESOURCE, not an identifier to look it up with.

    It used to be handed a ``ResourceRef`` — a ``(kind, name)`` pair — which is
    what made a kind's cleanup start from the label. The row itself is what
    replaced it: a hook that needs the identity reads ``resource.uid``, one
    that needs the label reads ``resource.name``, and neither has a lookup to
    get wrong.
    """
    calls: list[Resource] = []
    k = Kind(
        name="foo",
        display_name="Foo",
        config_schema=_FooConfig,
        on_delete=lambda resource: calls.append(resource),
    )
    assert k.on_delete is not None
    r = _resource()
    k.on_delete(r)
    assert calls == [r]
    assert calls[0].uid == "f00d1e55"


def test_kind_on_rename_hook_sees_the_resource_and_the_proposed_label():
    """``on_rename`` is the one thing a rename costs a kind, and the only hook
    that takes a second argument: the resource as it still stands, plus the
    name it is about to take. A kind whose name is also a directory moves it
    here, and raising aborts the rename."""
    calls: list[tuple[Resource, str]] = []
    k = Kind(
        name="foo",
        display_name="Foo",
        config_schema=_FooConfig,
        on_rename=lambda resource, new_name: calls.append((resource, new_name)),
    )
    assert k.on_rename is not None
    r = _resource(name="before")
    k.on_rename(r, "after")
    assert calls == [(r, "after")]
