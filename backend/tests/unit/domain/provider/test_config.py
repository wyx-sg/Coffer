"""ProviderConfig validation tests (spec provider-switching). Pure — unit tier."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from coffer.domain.provider.config import (
    Protocol,
    ProviderConfig,
)
from coffer.domain.provider.modality import Modality


def test_valid_config_defaults() -> None:
    c = ProviderConfig(
        protocol="anthropic",  # type: ignore[arg-type]
        base_url="https://x",
        secret_ref="provider/acme/key",
    )
    assert c.protocol is Protocol.ANTHROPIC
    assert c.transcribe_default is False


def test_a_stored_internal_default_is_accepted_and_ignored() -> None:
    c = ProviderConfig.model_validate(
        {
            "protocol": "openai",
            "base_url": "https://x",
            "secret_ref": "provider/acme/key",
            "internal_default": True,
        }
    )
    assert "internal_default" not in c.model_dump()


def test_unknown_protocol_member_is_valid() -> None:
    # ``unknown`` is a first-class protocol (the probe was inconclusive); a
    # connection with it still requires a secret like any cloud wire.
    c = ProviderConfig(
        protocol="unknown",  # type: ignore[arg-type]
        base_url="https://x",
        secret_ref="r",
    )
    assert c.protocol is Protocol.UNKNOWN


def test_bogus_protocol_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            protocol="bogus",  # type: ignore[arg-type]
            base_url="x",
            secret_ref="r",
        )


def test_empty_base_url_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            protocol="openai",  # type: ignore[arg-type]
            base_url="   ",
            secret_ref="r",
        )


def test_malformed_secret_ref_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            protocol="openai",  # type: ignore[arg-type]
            base_url="x",
            secret_ref="bad ref!",
        )


def test_a_stored_retired_ollama_connection_still_reads() -> None:
    """The ollama protocol is no longer offered, but a connection file that
    holds it stays readable (keyless, as it was written)."""
    c = ProviderConfig.model_validate({"protocol": "ollama", "base_url": "http://localhost:11434"})
    assert c.protocol.value == "ollama" and c.secret_ref is None


def test_cloud_protocol_requires_secret() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            protocol="openai",  # type: ignore[arg-type]
            base_url="x",
            secret_ref=None,
        )


def test_compatible_agents_is_no_longer_a_config_field() -> None:
    """The axis moved to the resource's framework scope, and the migration
    stripped the key — so a config still carrying it is rejected outright
    rather than silently ignored (no load-time shim)."""
    with pytest.raises(ValidationError):
        ProviderConfig(
            protocol="openai",  # type: ignore[arg-type]
            base_url="x",
            secret_ref="r",
            compatible_agents=["claude_code"],  # type: ignore[call-arg]
        )


def test_extra_field_forbidden() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            protocol="openai",  # type: ignore[arg-type]
            base_url="x",
            secret_ref="r",
            bogus=1,
        )


def test_models_defaults_to_unrestricted() -> None:
    # No curated set ⇒ empty ⇒ every model the endpoint serves is on offer.
    c = ProviderConfig(
        protocol="openai",  # type: ignore[arg-type]
        base_url="x",
        secret_ref="r",
    )
    assert c.models == []


def test_models_are_opaque_strings_kept_in_order() -> None:
    # Coffer writes down no model name of its own: whatever the user curated is
    # stored verbatim, in the order they chose, and never checked against a list.
    c = ProviderConfig(
        protocol="unknown",  # type: ignore[arg-type]
        base_url="x",
        secret_ref="r",
        models=[{"id": "agnes-2.0"}, {"id": "not-a-real-model"}, {"id": "gpt-5"}],
    )
    assert c.model_ids() == ["agnes-2.0", "not-a-real-model", "gpt-5"]


def test_models_default_to_text_modality() -> None:
    # The kind every curated set held before modalities existed, so an entry
    # that says nothing keeps behaving as a chat model.
    c = ProviderConfig(
        protocol="openai",  # type: ignore[arg-type]
        base_url="x",
        secret_ref="r",
        models=[{"id": "gpt-5"}],
    )
    assert c.models[0].modality is Modality.TEXT


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="curate an embedding model alongside chat models on one connection",
)
def test_one_connection_curates_several_modalities() -> None:
    # One endpoint, one key, several kinds of model: the curated set says which
    # is which, and each picker asks for the kind it serves.
    c = ProviderConfig(
        protocol="openai",  # type: ignore[arg-type]
        base_url="x",
        secret_ref="r",
        models=[
            {"id": "gpt-5"},
            {"id": "text-embedding-3-large", "modality": "embedding"},
            {"id": "dall-e-3", "modality": "image"},
        ],
    )
    assert c.model_ids(Modality.TEXT) == ["gpt-5"]
    assert c.model_ids(Modality.EMBEDDING) == ["text-embedding-3-large"]
    assert c.model_ids(Modality.IMAGE) == ["dall-e-3"]
    assert len(c.model_ids()) == 3


def test_stored_modality_is_not_re_inferred_on_load() -> None:
    # The user's answer beats any guess Coffer could make from the name: an id
    # that LOOKS like an embedding model stays whatever it was stored as.
    c = ProviderConfig(
        protocol="openai",  # type: ignore[arg-type]
        base_url="x",
        secret_ref="r",
        models=[{"id": "text-embedding-3-large", "modality": "text"}],
    )
    assert c.model_ids(Modality.TEXT) == ["text-embedding-3-large"]
    assert c.model_ids(Modality.EMBEDDING) == []


def test_models_dedupe_and_strip() -> None:
    c = ProviderConfig(
        protocol="openai",  # type: ignore[arg-type]
        base_url="x",
        secret_ref="r",
        models=[{"id": "gpt-5"}, {"id": " gpt-5 "}, {"id": "o3"}],
    )
    assert c.model_ids() == ["gpt-5", "o3"]


def test_blank_model_id_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            protocol="openai",  # type: ignore[arg-type]
            base_url="x",
            secret_ref="r",
            models=[{"id": "gpt-5"}, {"id": "   "}],
        )


def test_unknown_modality_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            protocol="openai",  # type: ignore[arg-type]
            base_url="x",
            secret_ref="r",
            models=[{"id": "gpt-5", "modality": "hologram"}],
        )


def test_absurd_model_ids_rejected() -> None:
    for models in ([{"id": "m" * 201}], [{"id": f"m{i}"} for i in range(201)]):
        with pytest.raises(ValidationError):
            ProviderConfig(
                protocol="openai",  # type: ignore[arg-type]
                base_url="x",
                secret_ref="r",
                models=models,
            )


def test_a_stored_ollama_connection_keeps_its_curated_models() -> None:
    c = ProviderConfig(
        protocol="ollama",  # type: ignore[arg-type]
        base_url="http://localhost:11434",
        models=[{"id": "qwen3:8b"}],
    )
    assert c.model_ids() == ["qwen3:8b"]


def test_a_curated_model_drops_the_retired_effort_keys() -> None:
    # Migration for the removal of reasoning effort: a stored entry may still
    # carry the keys, and the file loses them on its next write.
    c = ProviderConfig.model_validate(
        {
            "protocol": "openai",
            "base_url": "https://x",
            "secret_ref": "provider/acme/key",
            "models": [
                {"id": "m-1", "effort_levels": ["low", "high"], "default_effort": "low"},
            ],
        }
    )
    [model] = c.models
    assert model.id == "m-1"
    assert "effort_levels" not in model.model_dump()
    assert "default_effort" not in model.model_dump()


def _deepseek(**over: object) -> ProviderConfig:
    data: dict[str, object] = {
        "protocol": "openai",
        "base_url": "https://api.deepseek.com",
        "anthropic_base_url": "https://api.deepseek.com/anthropic",
        "secret_ref": "provider/ds/key",
    }
    data.update(over)
    return ProviderConfig.model_validate(data)


def test_an_openai_connection_with_an_anthropic_address_serves_both_wires() -> None:
    # ADR one-connection-serves-both-wires.
    c = _deepseek()
    assert c.served_wires() == {"anthropic", "openai"}
    assert c.base_url_for(anthropic=True) == "https://api.deepseek.com/anthropic"
    assert c.base_url_for(anthropic=False) == "https://api.deepseek.com"


def test_without_an_anthropic_address_a_connection_serves_its_own_wire_only() -> None:
    c = _deepseek(anthropic_base_url="  ")
    assert c.anthropic_base_url is None
    assert c.served_wires() == {"openai"}
    assert c.base_url_for(anthropic=True) == "https://api.deepseek.com"
    assert "anthropic_base_url" not in c.model_dump()
    anthropic = ProviderConfig(
        protocol=Protocol.ANTHROPIC, base_url="https://x", secret_ref="provider/a/key"
    )
    assert anthropic.served_wires() == {"anthropic"}


def test_an_unknown_wire_serves_both_and_the_switch_test_decides() -> None:
    c = ProviderConfig(protocol=Protocol.UNKNOWN, base_url="https://x", secret_ref="provider/a/key")
    assert c.served_wires() == {"anthropic", "openai"}


def test_only_a_remote_openai_connection_takes_an_anthropic_address() -> None:
    with pytest.raises(ValidationError, match="Anthropic address"):
        _deepseek(protocol="anthropic")
    with pytest.raises(ValidationError, match="Anthropic address"):
        _deepseek(
            base_url="http://127.0.0.1:1234/v1",
            local_runtime={"runtime": "lmstudio"},
        )
