"""Build a LangChain chat model from a provider connection (``ProviderConfig``).

This is the *only* module that may import ``langchain*`` or ``langgraph``
outside of ``coffer.infrastructure.chat`` (enforced by importlinter Contract 9).

Lazy per-provider imports prevent an ``ImportError`` when an optional
integration package is absent. Cloud connections (anthropic/openai) need an API
key resolved at call time via the injected ``credential_resolver``; ``ollama``
needs only its ``base_url``. Every connection carries a ``base_url`` (its
endpoint), which is passed to the client so a custom/proxy endpoint is honoured.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from coffer.domain.provider.config import ProviderConfig, WireFormat


def build_chat_model(
    config: ProviderConfig,
    credential_resolver: Callable[[str], str],
) -> Any:  # returns langchain_core.language_models.chat_models.BaseChatModel
    """Construct a LangChain ``BaseChatModel`` for the connection *config*.

    Args:
        config: The provider connection (wire format / model / base_url /
            credential_ref) describing what to build.
        credential_resolver: Callable that accepts a credential reference and
            returns the resolved secret (e.g. the raw API key). The composition
            root injects this so this module stays infrastructure-pure (no
            keyring import here).

    Returns:
        A LangChain ``BaseChatModel`` instance ready for use.

    Raises:
        ValueError: When the wire format is unknown or a required parameter
            (credential for a cloud wire) is missing.
        ImportError: When the required LangChain integration package is not
            installed.
    """
    wire = config.wire_format

    if wire is WireFormat.ANTHROPIC:
        return _build_anthropic(config, credential_resolver)
    if wire is WireFormat.OPENAI:
        return _build_openai(config, credential_resolver)
    if wire is WireFormat.OLLAMA:
        return _build_ollama(config)

    raise ValueError(f"Unsupported wire format: {wire!r}")  # pragma: no cover


# ---------------------------------------------------------------------------
# Per-wire builders (lazy imports)
# ---------------------------------------------------------------------------


def _build_anthropic(
    config: ProviderConfig,
    credential_resolver: Callable[[str], str],
) -> Any:
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError as exc:
        raise ImportError(
            "langchain-anthropic is required for the 'anthropic' wire format. "
            "Install it with: pip install langchain-anthropic"
        ) from exc

    if not config.credential_ref:
        raise ValueError("anthropic connection is missing credential_ref")

    api_key = credential_resolver(config.credential_ref)
    # base_url is the connection's endpoint (honoured for proxies / relays like
    # Kimi or DeepSeek); ``base_url`` is ChatAnthropic's populate-by-alias name.
    return ChatAnthropic(  # type: ignore[call-arg]
        model=config.model,
        api_key=api_key,  # type: ignore[arg-type]
        base_url=config.base_url,
    )


def _build_openai(
    config: ProviderConfig,
    credential_resolver: Callable[[str], str],
) -> Any:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise ImportError(
            "langchain-openai is required for the 'openai' wire format. "
            "Install it with: pip install langchain-openai"
        ) from exc

    if not config.credential_ref:
        raise ValueError("openai connection is missing credential_ref")

    api_key = credential_resolver(config.credential_ref)
    return ChatOpenAI(
        model=config.model,
        api_key=api_key,  # type: ignore[arg-type]
        base_url=config.base_url,
    )


def _build_ollama(config: ProviderConfig) -> Any:
    try:
        from langchain_ollama import ChatOllama
    except ImportError as exc:
        raise ImportError(
            "langchain-ollama is required for the 'ollama' wire format. "
            "Install it with: pip install langchain-ollama"
        ) from exc

    return ChatOllama(model=config.model, base_url=config.base_url)
