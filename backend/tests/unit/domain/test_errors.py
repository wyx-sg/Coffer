from coffer.domain.errors import (
    CofferError,
    ConfigValidationError,
    ResourceAlreadyExists,
    ResourceNotFound,
    UnknownKind,
)


def test_resource_not_found_carries_ref():
    err = ResourceNotFound("mcp_server", "filesystem")
    assert err.kind == "mcp_server"
    assert err.name == "filesystem"
    assert "mcp_server:filesystem" in str(err)
    assert isinstance(err, CofferError)
    assert err.code == "RESOURCE_NOT_FOUND"


def test_resource_already_exists_carries_ref():
    err = ResourceAlreadyExists("mcp_server", "filesystem")
    assert err.kind == "mcp_server"
    assert err.name == "filesystem"
    assert err.code == "RESOURCE_ALREADY_EXISTS"


def test_unknown_kind_carries_kind():
    err = UnknownKind("nope")
    assert err.kind == "nope"
    assert err.code == "UNKNOWN_KIND"
    assert isinstance(err, CofferError)


def test_config_validation_error_is_coffer_error():
    err = ConfigValidationError("bad config")
    assert err.code == "CONFIG_INVALID"
    assert isinstance(err, CofferError)
