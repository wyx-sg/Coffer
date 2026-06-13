"""One-shot LLM completion adapter (LlmCompletionPort).

Keeps langchain confined to infrastructure.chat (Contract 9).
"""

from __future__ import annotations

from collections.abc import Callable

from langchain_core.messages import HumanMessage, SystemMessage

from coffer.domain.chat.model import ModelConfig
from coffer.infrastructure.chat.langchain_models import build_chat_model


class LangchainLlmCompletion:
    """Implements LlmCompletionPort via LangChain's ainvoke."""

    async def complete(
        self,
        *,
        system: str,
        user: str,
        model: ModelConfig,
        credential_resolver: Callable[[str], str],
    ) -> str:
        chat = build_chat_model(model, credential_resolver)
        resp = await chat.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
        content = resp.content
        return content if isinstance(content, str) else str(content)
