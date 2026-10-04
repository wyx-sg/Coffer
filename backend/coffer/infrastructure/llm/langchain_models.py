"""Build a LangChain chat model from a resolved connection + model.

``coffer.infrastructure.llm`` is the only package that may import
``langchain*`` or ``langgraph`` at all, and this is the module inside it that
builds the model. ``coffer.infrastructure.chat`` — where these adapters lived
while the chat page was their only consumer — is explicitly forbidden one now
(importlinter Contract 9a).

Lazy per-provider imports prevent an ``ImportError`` when an optional
integration package is absent. Cloud connections (anthropic/openai) need an API
key resolved at call time via the injected ``secret_resolver``; ``ollama``
needs only its ``base_url``. Every connection carries a ``base_url`` (its
endpoint), which is passed to the client so a custom/proxy endpoint is honoured.
The model id lives apart from the connection (spec provider-switching "Take
projected model keys from the agent's binding") and arrives in the
``ResolvedConnection`` alongside it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from coffer.domain.provider.config import Protocol, ResolvedConnection
from coffer.infrastructure.net.redirects import stop_following_redirects


def build_chat_model(
    resolved: ResolvedConnection,
    secret_resolver: Callable[[str], str],
    *,
    timeout: float | None = None,
) -> Any:  # returns langchain_core.language_models.chat_models.BaseChatModel
    """Construct a LangChain ``BaseChatModel`` for *resolved*.

    Args:
        resolved: The connection (protocol / base_url / secret_ref) paired
            with the ``model`` id to run — the model lives apart from the
            connection (spec internal-engine "Resolve the engine's connection
            and model together"), so both are supplied together here.
        secret_resolver: Callable that accepts a secret reference and
            returns the resolved secret (e.g. the raw API key). The composition
            root injects this so this module stays infrastructure-pure (no
            keyring import here).
        timeout: Seconds one request to this model may take. Set on the CLIENT
            rather than around the call, which is the only place that reaches
            an agentic loop's individual turns — the loop is one ``await`` from
            the outside, so wrapping it would bound the whole conversation or
            nothing. ``None`` leaves each integration's own default in place.

    Returns:
        A LangChain ``BaseChatModel`` instance ready for use.

    Raises:
        ValueError: When a required parameter (the secret of a connection that
            is not a local runtime) is missing.
        ImportError: When the required LangChain integration package is not
            installed.
    """
    protocol = resolved.config.protocol

    if protocol is Protocol.ANTHROPIC:
        return _build_anthropic(resolved, secret_resolver, timeout)
    # ``unknown`` is a first-class wire (an endpoint the probe could not
    # classify); the engine drives it over the OpenAI-compatible API, as
    # speech-to-text already does.
    if protocol in (Protocol.OPENAI, Protocol.UNKNOWN):
        return _build_openai(resolved, secret_resolver, timeout)
    return _build_ollama(resolved, timeout)


#: What a keyless local runtime is given as an API key: the client libraries
#: refuse an empty one and a local server ignores it.
_LOCAL_PLACEHOLDER_KEY = "local"


def _api_key(
    resolved: ResolvedConnection, secret_resolver: Callable[[str], str], label: str
) -> str:
    """The connection's key; a placeholder for a local runtime that has none
    (its secret is optional, spec provider-switching "Make the secret optional
    for ollama and local runtimes")."""
    config = resolved.config
    if config.secret_ref:
        return secret_resolver(config.secret_ref)
    if config.local_runtime is not None:
        return _LOCAL_PLACEHOLDER_KEY
    raise ValueError(f"{label} connection is missing secret_ref")


# ---------------------------------------------------------------------------
# Per-protocol builders (lazy imports)
# ---------------------------------------------------------------------------


def _build_anthropic(
    resolved: ResolvedConnection,
    secret_resolver: Callable[[str], str],
    timeout: float | None = None,
) -> Any:
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError as exc:
        raise ImportError(
            "langchain-anthropic is required for the 'anthropic' protocol. "
            "Install it with: pip install langchain-anthropic"
        ) from exc

    config = resolved.config
    api_key = _api_key(resolved, secret_resolver, "anthropic")
    # base_url is the connection's endpoint (honoured for proxies / relays like
    # Kimi or DeepSeek); ``base_url`` is ChatAnthropic's populate-by-alias name.
    model = ChatAnthropic(  # type: ignore[call-arg]
        model=resolved.model,
        api_key=api_key,  # type: ignore[arg-type]
        base_url=config.base_url,
        timeout=timeout,
    )
    # The SDK's own client follows redirects and sends the key as ``x-api-key``,
    # which httpx does not strip across origins (spec secret "Send a secret only
    # to the origin it was approved for").
    for sdk in (model._client, model._async_client):
        stop_following_redirects(sdk._client)
    return model


def _build_openai(
    resolved: ResolvedConnection,
    secret_resolver: Callable[[str], str],
    timeout: float | None = None,
) -> Any:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise ImportError(
            "langchain-openai is required for the 'openai' protocol. "
            "Install it with: pip install langchain-openai"
        ) from exc

    from openai import DefaultAsyncHttpxClient, DefaultHttpxClient

    config = resolved.config
    api_key = _api_key(resolved, secret_resolver, "openai")
    # ``base_url`` lets an OpenAI-COMPATIBLE endpoint (Azure/OpenRouter/aggregators)
    # be used; ``None`` falls back to the official OpenAI API. Without this an
    # openai-compatible provider's calls silently hit api.openai.com and 401.
    return ChatOpenAI(
        model=resolved.model,
        api_key=api_key,  # type: ignore[arg-type]
        base_url=config.base_url or None,
        timeout=timeout,
        # The SDK's default client follows redirects; the key must not (spec
        # secret "Send a secret only to the origin it was approved for").
        http_client=DefaultHttpxClient(follow_redirects=False),
        http_async_client=DefaultAsyncHttpxClient(follow_redirects=False),
    )


def _build_ollama(resolved: ResolvedConnection, timeout: float | None = None) -> Any:
    try:
        from langchain_ollama import ChatOllama
    except ImportError as exc:
        raise ImportError(
            "langchain-ollama is required for the 'ollama' protocol. "
            "Install it with: pip install langchain-ollama"
        ) from exc

    # ``ChatOllama`` takes no ``timeout`` of its own; the bound goes to the
    # underlying httpx client it builds, which is the same place the other two
    # integrations put theirs. ``None`` leaves the client's own default.
    client_kwargs: dict[str, Any] = {"follow_redirects": False}
    if timeout is not None:
        client_kwargs["timeout"] = timeout
    return ChatOllama(
        model=resolved.model,
        base_url=resolved.config.base_url,
        client_kwargs=client_kwargs,
    )
