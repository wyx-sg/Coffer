import pytest

from coffer.domain.resource import ResourceRef


def test_parse_round_trip():
    ref = ResourceRef.parse("mcp_server:filesystem")
    assert ref == ResourceRef("mcp_server", "filesystem")
    assert str(ref) == "mcp_server:filesystem"


@pytest.mark.parametrize("bad", ["", "no_colon", ":missing_kind", "kind:", "a:b:c"])
def test_invalid_strings_rejected(bad):
    with pytest.raises(ValueError):
        ResourceRef.parse(bad)


def test_frozen_and_hashable():
    a = ResourceRef("k", "n")
    {a}  # hashable  # noqa: B018
    with pytest.raises((AttributeError, TypeError)):
        a.kind = "x"  # type: ignore[misc]  # frozen


@pytest.mark.parametrize(
    "invalid_name",
    [
        "bad name",  # space
        "bad/name",  # slash
        "café",  # non-ASCII
        "bad!name",  # exclamation
        "bad@name",  # at sign
    ],
)
def test_resource_ref_rejects_invalid_name_chars(invalid_name):
    """D5: resource names must match ^[a-zA-Z0-9_.-]+$."""
    with pytest.raises(ValueError):
        ResourceRef("mcp_server", invalid_name)


def test_resource_ref_rejects_name_over_64():
    """D5: resource names are capped at 64 characters."""
    long_name = "a" * 65
    with pytest.raises(ValueError):
        ResourceRef("mcp_server", long_name)


def test_resource_ref_accepts_valid_names():
    """D5: names with letters, digits, underscores, dots, hyphens are fine."""
    for valid in ["simple", "with-dash", "with_underscore", "with.dot", "ABC123"]:
        ref = ResourceRef("mcp_server", valid)
        assert ref.name == valid
