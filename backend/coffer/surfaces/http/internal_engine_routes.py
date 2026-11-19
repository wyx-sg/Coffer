# backend/coffer/surfaces/http/internal_engine_routes.py
"""/api/v1/internal-engine-config — Coffer's own operating settings.

One thing lives on the singleton: which model transcribes speech (spec
internal-engine "Transcribe speech on its own connection and model"). It is a
property of the operator's endpoint rather than of Coffer, and writes on its
own route."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from coffer.application.internal_engine_config_service import InternalEngineConfigService
from coffer.domain.internal_engine_config import GlobalInternalEngineConfig
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor, get_internal_engine_config_service

# The request/response models live here rather than in ``schemas.py``, which is
# at its size ceiling, and it keeps a shape next to the one route that builds it.


class InternalEngineConfigOut(BaseModel):
    """Coffer's own operating settings: its speech-to-text."""

    updated_at: datetime | None = None
    #: The speech-to-text model. ``null`` means Coffer transcribes nothing and
    #: hands the agent the audio file untouched — a real answer, not an unset
    #: one, and the same answer as no connection marked ``transcribe_default``.
    transcribe_model: str | None = None


class TranscribeModelUpdate(BaseModel):
    """Choose the speech-to-text model; ``null``/empty stops transcription.

    Transcription runs on the connection marked ``transcribe_default`` alone: a
    gateway that serves chat completions commonly serves no transcription
    endpoint.
    """

    model: str | None = None


router = APIRouter(
    prefix="/api/v1/internal-engine-config",
    tags=["internal-engine"],
    dependencies=[Depends(require_token)],
)


def _to_out(cfg: GlobalInternalEngineConfig) -> InternalEngineConfigOut:
    return InternalEngineConfigOut(updated_at=cfg.updated_at, transcribe_model=cfg.transcribe_model)


@router.get("", response_model=InternalEngineConfigOut)
async def get_config(
    svc: InternalEngineConfigService = Depends(get_internal_engine_config_service),  # noqa: B008
) -> InternalEngineConfigOut:
    return _to_out(await svc.get())


@router.put("/transcribe-model", response_model=InternalEngineConfigOut)
async def update_transcribe_model(
    body: TranscribeModelUpdate,
    svc: InternalEngineConfigService = Depends(get_internal_engine_config_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> InternalEngineConfigOut:
    """Choose the model Coffer transcribes speech with, or stop transcribing.

    Clearing it is an operating decision an operator may want — with no model
    the recording never leaves the machine — which is why it is expressed here
    rather than by deleting the connection that carries the endpoint.
    """
    return _to_out(await svc.set_transcribe_model(body.model, actor=actor))
