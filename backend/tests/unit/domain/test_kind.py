from pydantic import BaseModel

from coffer.domain.resource import Kind, ResourceRef


class _FooConfig(BaseModel):
    x: int


def test_kind_basic():
    k = Kind(name="foo", display_name="Foo", config_schema=_FooConfig)
    assert k.name == "foo"
    assert k.config_schema is _FooConfig
    assert k.on_delete is None


def test_kind_on_delete_hook():
    calls: list[ResourceRef] = []
    k = Kind(
        name="foo",
        display_name="Foo",
        config_schema=_FooConfig,
        on_delete=lambda ref: calls.append(ref),
    )
    assert k.on_delete is not None
    k.on_delete(ResourceRef("foo", "bar"))
    assert calls == [ResourceRef("foo", "bar")]
