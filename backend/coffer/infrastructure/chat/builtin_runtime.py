"""BuiltinRuntime — Coffer's own LLM loop, engine LangGraph.

The only module that imports LangChain/LangGraph (importlinter Contract 7), and
even here the imports are lazy (inside ``stream``) so constructing the runtime —
and resolving credentials — never requires the engine to be importable. The
provider/model string is resolved with ``init_chat_model`` so any mainstream
provider works; gateway tools are loaded from Coffer's own ``/mcp`` endpoint via
``langchain-mcp-adapters``.

Streaming + tool events + human-in-the-loop confirmation are mapped onto the
``AgentRuntime`` port. The port's behavioural contract (including confirmation,
stop, error handling) is validated at the application layer with a fake runtime;
this concrete engine adapter is exercised end-to-end against a real provider in
the (deferred) e2e tier, since it needs a live model + key.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

from coffer.domain.builtin_agent.config import BuiltinAgentConfig
from coffer.domain.chat.runtime import (
    ChatTurnRequest,
    ConfirmationRequest,
    DoneEvent,
    ErrorEvent,
    RuntimeEvent,
    TextDelta,
    ToolCallStarted,
    ToolResultEvent,
)
from coffer.domain.errors import LlmNotConfigured

# Cloud providers that require an API key; local ones (ollama) do not.
_PROVIDER_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}

_DONE = object()  # queue sentinel


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts)
    return ""


class BuiltinRuntime:
    def __init__(
        self,
        *,
        config: dict[str, Any],
        gateway_url: str | None,
        gateway_token: str | None,
        keyring: Any,
    ) -> None:
        cfg = BuiltinAgentConfig.model_validate(config)
        provider, _, _ = cfg.model.partition(":")
        api_key: str | None = None
        if cfg.credential_ref is not None and keyring is not None:
            api_key = keyring.get(cfg.credential_ref)
        # A cloud provider with neither a stored credential nor an environment
        # key cannot run — fail fast (503) before any message is persisted.
        if (
            provider in _PROVIDER_ENV
            and not api_key
            and not os.environ.get(_PROVIDER_ENV[provider])
        ):
            raise LlmNotConfigured(f"no API key for provider {provider!r} (model {cfg.model!r})")
        self._cfg = cfg
        self._provider = provider
        self._api_key = api_key
        self._gateway_url = gateway_url if cfg.use_gateway else None
        self._gateway_token = gateway_token
        self._stopped = asyncio.Event()
        self._decisions: dict[str, asyncio.Future[bool]] = {}
        self._queue: asyncio.Queue[Any] | None = None

    async def _load_tools(self) -> list[Any]:
        if not self._gateway_url:
            return []
        from langchain_mcp_adapters.client import MultiServerMCPClient

        headers = {"X-Coffer-Token": self._gateway_token} if self._gateway_token else {}
        client = MultiServerMCPClient(
            {
                "coffer": {
                    "url": self._gateway_url,
                    "transport": "streamable_http",
                    "headers": headers,
                }
            }
        )
        tools = await client.get_tools()
        return [self._maybe_gate(t) for t in tools]

    def _maybe_gate(self, tool: Any) -> Any:
        """Wrap a tool whose name matches the confirm policy so it pauses for a
        human decision before running."""
        name = getattr(tool, "name", "")
        if not self._cfg.requires_confirmation(name):
            return tool
        original = tool.coroutine

        async def _gated(**kwargs: Any) -> Any:
            rid = uuid.uuid4().hex
            loop = asyncio.get_running_loop()
            fut: asyncio.Future[bool] = loop.create_future()
            self._decisions[rid] = fut
            assert self._queue is not None
            await self._queue.put(ConfirmationRequest(id=rid, tool=name, args=dict(kwargs)))
            approved = await fut
            await self._queue.put(
                ToolResultEvent(
                    id=rid, tool=name, ok=approved, summary="ran" if approved else "declined"
                )
            )
            if not approved:
                return "The user declined to run this tool."
            if original is not None:
                return await original(**kwargs)
            return tool.func(**kwargs)

        return tool.model_copy(update={"coroutine": _gated})

    def _map_event(self, event: Any) -> list[RuntimeEvent]:
        kind = event.get("event")
        if kind == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            text = _content_text(getattr(chunk, "content", "")) if chunk is not None else ""
            return [TextDelta(text=text)] if text else []
        if kind == "on_tool_start":
            return [
                ToolCallStarted(
                    id=str(event.get("run_id", "")),
                    tool=str(event.get("name", "")),
                    args=event.get("data", {}).get("input") or {},
                )
            ]
        if kind == "on_tool_end":
            out = event.get("data", {}).get("output")
            return [
                ToolResultEvent(
                    id=str(event.get("run_id", "")),
                    tool=str(event.get("name", "")),
                    ok=True,
                    summary=str(out)[:200],
                )
            ]
        return []

    async def stream(self, request: ChatTurnRequest) -> AsyncIterator[RuntimeEvent]:
        from langchain.chat_models import init_chat_model
        from langgraph.prebuilt import create_react_agent

        kwargs: dict[str, Any] = {}
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if self._cfg.temperature is not None:
            kwargs["temperature"] = self._cfg.temperature
        if self._cfg.max_tokens is not None:
            kwargs["max_tokens"] = self._cfg.max_tokens

        try:
            model = init_chat_model(self._cfg.model, **kwargs)
            tools = await self._load_tools()
            agent = create_react_agent(model, tools)
        except Exception as e:  # engine / connection setup failure
            yield ErrorEvent(code="UPSTREAM_UNAVAILABLE", message=str(e)[:200])
            return

        messages: list[tuple[str, str]] = []
        if self._cfg.system_prompt:
            messages.append(("system", self._cfg.system_prompt))
        messages.extend((m.role, m.content) for m in request.history)
        messages.append(("user", request.user_message))

        queue: asyncio.Queue[Any] = asyncio.Queue()
        self._queue = queue

        async def _produce() -> None:
            try:
                async for event in agent.astream_events({"messages": messages}, version="v2"):
                    if self._stopped.is_set():
                        break
                    for ev in self._map_event(event):
                        await queue.put(ev)
            except Exception as e:
                await queue.put(ErrorEvent(code="UPSTREAM_UNAVAILABLE", message=str(e)[:200]))
            finally:
                await queue.put(_DONE)

        task = asyncio.create_task(_produce())
        try:
            while True:
                item = await queue.get()
                if item is _DONE:
                    break
                yield item
                if self._stopped.is_set():
                    break
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        yield DoneEvent()

    async def resolve_confirmation(self, request_id: str, approve: bool) -> None:
        fut = self._decisions.get(request_id)
        if fut is not None and not fut.done():
            fut.set_result(approve)

    async def stop(self) -> None:
        self._stopped.set()
        for fut in self._decisions.values():
            if not fut.done():
                fut.set_result(False)
