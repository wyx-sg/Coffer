from pydantic import BaseModel

from coffer.domain.kind_module import KindModule


class _FooConfig(BaseModel):
    x: int


def test_kind_module_minimal():
    km = KindModule(
        name="foo",
        display_name="Foo",
        config_schema=_FooConfig,
    )
    assert km.name == "foo"
    assert km.display_name == "Foo"
    assert km.config_schema is _FooConfig
    assert km.on_delete is None
    assert km.http_routers == ()
    assert km.cli_groups == ()


def test_kind_module_frozen():
    km = KindModule(name="foo", display_name="Foo", config_schema=_FooConfig)
    import pytest

    with pytest.raises((AttributeError, TypeError)):
        km.name = "bar"  # type: ignore[misc]
