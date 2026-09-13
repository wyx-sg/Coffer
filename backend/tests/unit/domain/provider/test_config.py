"""ProviderConfig validation tests (spec provider-switching). Pure — unit tier."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from coffer.domain.provider.config import (
    Protocol,
    ProviderConfig,
    default_scope_for_protocol,
)
from coffer.domain.provider.modality import Modality


def test_valid_config_defaults() -> None:
    c = ProviderConfig(
        protocol="anthropic",  # type: ignore[arg-type]
        base_url="https://x",
        credential_ref="provider/acme/key",
    )
    assert c.protocol is Protocol.ANTHROPIC
    assert c.is_active is False
    assert c.internal_default is False


def test_unknown_protocol_member_is_valid() -> None:
    # ``unknown`` is a first-class protocol (the probe was inconclusive); a
    # connection with it still requires a credential like any cloud wire.
    c = ProviderConfig(
        protocol="unknown",  # type: ignore[arg-type]
        base_url="https://x",
        credential_ref="r",
    )
    assert c.protocol is Protocol.UNKNOWN


def test_bogus_protocol_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            protocol="bogus",  # type: ignore[arg-type]
            base_url="x",
            credential_ref="r",
        )


def test_empty_base_url_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            protocol="openai",  # type: ignore[arg-type]
            base_url="   ",
            credential_ref="r",
        )


def test_malformed_credential_ref_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            protocol="openai",  # type: ignore[arg-type]
            base_url="x",
            credential_ref="bad ref!",
        )


def test_ollama_must_not_carry_credential() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            protocol="ollama",  # type: ignore[arg-type]
            base_url="http://localhost:11434",
            credential_ref="r",
        )


def test_cloud_protocol_requires_credential() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            protocol="openai",  # type: ignore[arg-type]
            base_url="x",
            credential_ref=None,
        )


def test_default_scope_by_protocol() -> None:
    """The scope a connection is CREATED with, by wire.

    This is the value the ``provider`` Kind pre-fills at registration
    (ADR per-agent-resource-scope): it replaces the ``compatible_agents``
    field the config used to carry, and it is a starting point only — the
    user re-targets a connection through the framework's scope surface.
    """
    # A credentialed endpoint starts open to every agent; the protocol decides
    # introspection and key handling, not who may be driven by it.
    assert default_scope_for_protocol("anthropic") == ["claude_code", "codex"]
    assert default_scope_for_protocol("openai") == ["claude_code", "codex"]
    # unknown starts open too; the user narrows it.
    assert default_scope_for_protocol("unknown") == ["claude_code", "codex"]
    # ollama is internal-only: it starts scoped to no agent at all.
    assert default_scope_for_protocol("ollama") == []
    # An unrecognised wire is treated like ``unknown`` rather than crashing.
    assert default_scope_for_protocol("martian") == ["claude_code", "codex"]


def test_compatible_agents_is_no_longer_a_config_field() -> None:
    """The axis moved to the resource's framework scope, and the migration
    stripped the key — so a config still carrying it is rejected outright
    rather than silently ignored (no load-time shim)."""
    with pytest.raises(ValidationError):
        ProviderConfig(
            protocol="openai",  # type: ignore[arg-type]
            base_url="x",
            credential_ref="r",
            compatible_agents=["claude_code"],  # type: ignore[call-arg]
        )


def test_ollama_still_refuses_a_credential() -> None:
    """The one wire rule that survives on the config: a keyless connection
    holds no credential ref. That it projects into no agent is now its empty
    starting scope, enforced at the projection seam, not here."""
    with pytest.raises(ValidationError):
        ProviderConfig(
            protocol="ollama",  # type: ignore[arg-type]
            base_url="http://x",
            credential_ref="r",
        )


def test_extra_field_forbidden() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            protocol="openai",  # type: ignore[arg-type]
            base_url="x",
            credential_ref="r",
            bogus=1,
        )


def test_models_defaults_to_unrestricted() -> None:
    # No curated set ⇒ empty ⇒ every model the endpoint serves is on offer.
    c = ProviderConfig(
        protocol="openai",  # type: ignore[arg-type]
        base_url="x",
        credential_ref="r",
    )
    assert c.models == []


def test_models_are_opaque_strings_kept_in_order() -> None:
    # Coffer writes down no model name of its own: whatever the user curated is
    # stored verbatim, in the order they chose, and never checked against a list.
    c = ProviderConfig(
        protocol="unknown",  # type: ignore[arg-type]
        base_url="x",
        credential_ref="r",
        models=[{"id": "agnes-2.0"}, {"id": "not-a-real-model"}, {"id": "gpt-5"}],
    )
    assert c.model_ids() == ["agnes-2.0", "not-a-real-model", "gpt-5"]


def test_models_default_to_text_modality() -> None:
    # The kind every curated set held before modalities existed, so an entry
    # that says nothing keeps behaving as a chat model.
    c = ProviderConfig(
        protocol="openai",  # type: ignore[arg-type]
        base_url="x",
        credential_ref="r",
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
        credential_ref="r",
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
        credential_ref="r",
        models=[{"id": "text-embedding-3-large", "modality": "text"}],
    )
    assert c.model_ids(Modality.TEXT) == ["text-embedding-3-large"]
    assert c.model_ids(Modality.EMBEDDING) == []


def test_models_dedupe_and_strip() -> None:
    c = ProviderConfig(
        protocol="openai",  # type: ignore[arg-type]
        base_url="x",
        credential_ref="r",
        models=[{"id": "gpt-5"}, {"id": " gpt-5 "}, {"id": "o3"}],
    )
    assert c.model_ids() == ["gpt-5", "o3"]


def test_blank_model_id_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            protocol="openai",  # type: ignore[arg-type]
            base_url="x",
            credential_ref="r",
            models=[{"id": "gpt-5"}, {"id": "   "}],
        )


def test_unknown_modality_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            protocol="openai",  # type: ignore[arg-type]
            base_url="x",
            credential_ref="r",
            models=[{"id": "gpt-5", "modality": "hologram"}],
        )


def test_absurd_model_ids_rejected() -> None:
    for models in ([{"id": "m" * 201}], [{"id": f"m{i}"} for i in range(201)]):
        with pytest.raises(ValidationError):
            ProviderConfig(
                protocol="openai",  # type: ignore[arg-type]
                base_url="x",
                credential_ref="r",
                models=models,
            )


def test_ollama_may_curate_models() -> None:
    # ollama projects into no agent, but the internal engine still picks a model
    # from it — so curating that endpoint's list is meaningful.
    c = ProviderConfig(
        protocol="ollama",  # type: ignore[arg-type]
        base_url="http://localhost:11434",
        models=[{"id": "qwen3:8b"}],
    )
    assert c.model_ids() == ["qwen3:8b"]
