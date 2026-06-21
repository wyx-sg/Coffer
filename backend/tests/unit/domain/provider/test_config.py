"""ProviderConfig validation tests (spec 011). Pure — unit tier."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from coffer.domain.provider.config import ProviderConfig, WireApi, WireFormat


def test_valid_config_defaults() -> None:
    c = ProviderConfig(
        wire_format="anthropic",  # type: ignore[arg-type]
        base_url="https://x",
        credential_ref="provider/acme/key",
        model="m",
    )
    assert c.wire_format is WireFormat.ANTHROPIC
    # Default wire_api is `responses`: codex-cli 0.130 dropped support for
    # `wire_api = "chat"` (config fails to load), so a connection created without
    # an explicit wire_api must project the value current Codex accepts.
    assert c.wire_api is WireApi.RESPONSES
    assert c.is_active is False
    assert c.fast_model is None


def test_unknown_wire_format_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            wire_format="bogus",  # type: ignore[arg-type]
            base_url="x",
            credential_ref="r",
            model="m",
        )


def test_empty_base_url_or_model_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            wire_format="openai",  # type: ignore[arg-type]
            base_url="   ",
            credential_ref="r",
            model="m",
        )
    with pytest.raises(ValidationError):
        ProviderConfig(
            wire_format="openai",  # type: ignore[arg-type]
            base_url="x",
            credential_ref="r",
            model="",
        )


def test_malformed_credential_ref_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            wire_format="openai",  # type: ignore[arg-type]
            base_url="x",
            credential_ref="bad ref!",
            model="m",
        )


def test_extra_field_forbidden() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            wire_format="openai",  # type: ignore[arg-type]
            base_url="x",
            credential_ref="r",
            model="m",
            bogus=1,
        )
