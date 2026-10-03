"""/api/v1/chat/conversations/{id}/agent-config — a conversation's agent config.

Included into the conversation router, which supplies the prefix and the token
dependency.
"""

from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, Depends

from coffer.application.chat.service import ChatService
from coffer.surfaces.http.chat.dependencies import get_chat_service
from coffer.surfaces.http.chat.schemas import AgentConfigOut, AgentConfigPatch

router = APIRouter()


@router.get("/conversations/{id}/agent-config", response_model=AgentConfigOut)
async def get_agent_config(
    id: str,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
) -> AgentConfigOut:
    """Read a conversation's agent config (cwd, model, effort). 404 if not found.

    ``session_id`` is provider-internal and deliberately not surfaced.
    """
    cfg = await svc.get_agent_config(id)  # raises ConversationNotFound -> 404
    return AgentConfigOut(cwd=cfg.cwd, model=cfg.model, effort=cfg.effort)


@router.patch("/conversations/{id}/agent-config", response_model=AgentConfigOut)
async def set_agent_config(
    id: str,
    body: AgentConfigPatch,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
) -> AgentConfigOut:
    """Set a managed agent's own model and effort for a conversation (ADR
    coffer-model-is-an-internal-engine → ADR model-catalogue-read-from-the-agent).

    Mirrors the channel ``/model`` command: read-then-``replace`` so ``cwd`` and
    ``session_id`` are preserved, and a body that mentions only one of the two
    leaves the other where it was. An empty/whitespace ``model`` clears the
    override (the conversation then inherits the active provider profile's
    projected default); an empty/whitespace ``effort`` clears it (the agent then
    runs at whatever its own config says).
    """
    cfg = await svc.get_agent_config(id)  # raises ConversationNotFound -> 404
    fields: dict[str, str | None] = {}
    if "model" in body.model_fields_set:
        fields["model"] = (body.model or "").strip() or None
    if "effort" in body.model_fields_set:
        fields["effort"] = (body.effort or "").strip() or None
    if fields:
        cfg = replace(cfg, **fields)
        await svc.set_agent_config(id, cfg)
    return AgentConfigOut(cwd=cfg.cwd, model=cfg.model, effort=cfg.effort)
