"""Build a LangChain chat model from a ``ModelConfig``.

This is the *only* module that may import ``langchain*`` or ``langgraph``
outside of ``coffer.infrastructure.chat`` (enforced by importlinter Contract 9).

Lazy per-provider imports prevent an ``ImportError`` when an optional
integration package is absent.  Cloud providers need an API key resolved
at call time via the injected ``credential_resolver``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from coffer.domain.chat.model import ModelConfig, ProviderType


def build_chat_model(
    config: ModelConfig,
    credential_resolver: Callable[[str], str],
) -> Any:  # returns langchain_core.language_models.chat_models.BaseChatModel
    """Construct a LangChain ``BaseChatModel`` for *config*.

    Args:
        config: The domain ``ModelConfig`` describing the provider/model.
        credential_resolver: Callable that accepts a credential reference
            string and returns the resolved secret (e.g. the raw API key).
            Do NOT import the keyring adapter here — the composition root
            injects this callable so this module stays infrastructure-pure.

    Returns:
        A LangChain ``BaseChatModel`` instance ready for use.

    Raises:
        ValueError: When the provider is unknown or a required parameter
            (credential or base_url) is missing.
        ImportError: When the required LangChain integration package is not
            installed.
    """
    provider = config.provider

    if provider == ProviderType.ANTHROPIC:
        return _build_anthropic(config, credential_resolver)
    if provider == ProviderType.OPENAI:
        return _build_openai(config, credential_resolver)
    if provider == ProviderType.OLLAMA:
        return _build_ollama(config)

    raise ValueError(f"Unsupported provider: {provider!r}")  # pragma: no cover


# ---------------------------------------------------------------------------
# Per-provider builders (lazy imports)
# ---------------------------------------------------------------------------


def _build_anthropic(
    config: ModelConfig,
    credential_resolver: Callable[[str], str],
) -> Any:
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError as exc:
        raise ImportError(
            "langchain-anthropic is required for the 'anthropic' provider. "
            "Install it with: pip install langchain-anthropic"
        ) from exc

    if not config.credential_ref:
        raise ValueError("ModelConfig for provider 'anthropic' is missing credential_ref")

    api_key = credential_resolver(config.credential_ref)
    return ChatAnthropic(model=config.model, api_key=api_key)  # type: ignore[arg-type, call-arg]


def _build_openai(
    config: ModelConfig,
    credential_resolver: Callable[[str], str],
) -> Any:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise ImportError(
            "langchain-openai is required for the 'openai' provider. "
            "Install it with: pip install langchain-openai"
        ) from exc

    if not config.credential_ref:
        raise ValueError("ModelConfig for provider 'openai' is missing credential_ref")

    api_key = credential_resolver(config.credential_ref)
    return ChatOpenAI(model=config.model, api_key=api_key)  # type: ignore[arg-type]


def _build_ollama(config: ModelConfig) -> Any:
    try:
        from langchain_ollama import ChatOllama
    except ImportError as exc:
        raise ImportError(
            "langchain-ollama is required for the 'ollama' provider. "
            "Install it with: pip install langchain-ollama"
        ) from exc

    if not config.base_url:
        raise ValueError("ModelConfig for provider 'ollama' is missing base_url")

    return ChatOllama(model=config.model, base_url=config.base_url)
