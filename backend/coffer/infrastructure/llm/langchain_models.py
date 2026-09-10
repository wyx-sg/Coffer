"""Build a LangChain chat model from a resolved connection + model.

This is the *only* module that may import ``langchain*`` or ``langgraph``
outside of ``coffer.infrastructure.chat`` (enforced by importlinter Contract 9).

Lazy per-provider imports prevent an ``ImportError`` when an optional
integration package is absent. Cloud connections (anthropic/openai) need an API
key resolved at call time via the injected ``credential_resolver``; ``ollama``
needs only its ``base_url``. Every connection carries a ``base_url`` (its
endpoint), which is passed to the client so a custom/proxy endpoint is honoured.
The model id lives apart from the connection (spec 011 E3) and arrives in the
``ResolvedConnection`` alongside it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from coffer.domain.provider.config import Protocol, ResolvedConnection


def build_chat_model(
    resolved: ResolvedConnection,
    credential_resolver: Callable[[str], str],
) -> Any:  # returns langchain_core.language_models.chat_models.BaseChatModel
    """Construct a LangChain ``BaseChatModel`` for *resolved*.

    Args:
        resolved: The connection (protocol / base_url / credential_ref) paired
            with the ``model`` id to run — the model lives apart from the
            connection (spec 011 E3), so both are supplied together here.
        credential_resolver: Callable that accepts a credential reference and
            returns the resolved secret (e.g. the raw API key). The composition
            root injects this so this module stays infrastructure-pure (no
            keyring import here).

    Returns:
        A LangChain ``BaseChatModel`` instance ready for use.

    Raises:
        ValueError: When the protocol is unsupported or a required parameter
            (credential for a cloud wire) is missing.
        ImportError: When the required LangChain integration package is not
            installed.
    """
    protocol = resolved.config.protocol

    if protocol is Protocol.ANTHROPIC:
        return _build_anthropic(resolved, credential_resolver)
    if protocol is Protocol.OPENAI:
        return _build_openai(resolved, credential_resolver)
    if protocol is Protocol.OLLAMA:
        return _build_ollama(resolved)

    raise ValueError(f"Unsupported protocol: {protocol!r}")  # pragma: no cover


# ---------------------------------------------------------------------------
# Per-protocol builders (lazy imports)
# ---------------------------------------------------------------------------


def _build_anthropic(
    resolved: ResolvedConnection,
    credential_resolver: Callable[[str], str],
) -> Any:
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError as exc:
        raise ImportError(
            "langchain-anthropic is required for the 'anthropic' protocol. "
            "Install it with: pip install langchain-anthropic"
        ) from exc

    config = resolved.config
    if not config.credential_ref:
        raise ValueError("anthropic connection is missing credential_ref")

    api_key = credential_resolver(config.credential_ref)
    # base_url is the connection's endpoint (honoured for proxies / relays like
    # Kimi or DeepSeek); ``base_url`` is ChatAnthropic's populate-by-alias name.
    return ChatAnthropic(  # type: ignore[call-arg]
        model=resolved.model,
        api_key=api_key,  # type: ignore[arg-type]
        base_url=config.base_url,
    )


def _build_openai(
    resolved: ResolvedConnection,
    credential_resolver: Callable[[str], str],
) -> Any:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise ImportError(
            "langchain-openai is required for the 'openai' protocol. "
            "Install it with: pip install langchain-openai"
        ) from exc

    config = resolved.config
    if not config.credential_ref:
        raise ValueError("openai connection is missing credential_ref")

    api_key = credential_resolver(config.credential_ref)
    # ``base_url`` lets an OpenAI-COMPATIBLE endpoint (Azure/OpenRouter/aggregators)
    # be used; ``None`` falls back to the official OpenAI API. Without this an
    # openai-compatible provider's calls silently hit api.openai.com and 401.
    return ChatOpenAI(
        model=resolved.model,
        api_key=api_key,  # type: ignore[arg-type]
        base_url=config.base_url or None,
    )


def _build_ollama(resolved: ResolvedConnection) -> Any:
    try:
        from langchain_ollama import ChatOllama
    except ImportError as exc:
        raise ImportError(
            "langchain-ollama is required for the 'ollama' protocol. "
            "Install it with: pip install langchain-ollama"
        ) from exc

    return ChatOllama(model=resolved.model, base_url=resolved.config.base_url)
