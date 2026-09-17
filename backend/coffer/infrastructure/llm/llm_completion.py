"""One-shot LLM completion adapter (LlmCompletionPort).

Keeps langchain confined to ``infrastructure.llm`` (Contract 9a).
"""

from __future__ import annotations

from collections.abc import Callable

from langchain_core.messages import HumanMessage, SystemMessage

from coffer.domain.provider.config import ResolvedConnection
from coffer.infrastructure.llm.langchain_models import build_chat_model


class LangchainLlmCompletion:
    """Implements LlmCompletionPort via LangChain's ainvoke."""

    async def complete(
        self,
        *,
        system: str,
        user: str,
        model: ResolvedConnection,
        credential_resolver: Callable[[str], str],
        timeout: float | None = None,
    ) -> str:
        chat = build_chat_model(model, credential_resolver, timeout=timeout)
        resp = await chat.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
        content = resp.content
        return content if isinstance(content, str) else str(content)
