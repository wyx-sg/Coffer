# backend/coffer/surfaces/http/internal_engine_routes.py
"""/api/v1/internal-engine-config — Coffer's own operating settings.

Two things live on one singleton: the unattended work Coffer runs on a
timer, and which model transcribes speech. The timed work is aggregation (spec
memory "Aggregate on an interval and on demand") and distil (spec memory
"Distil each raw entry into a note mechanically"),
each with a switch and an interval the operator can see and change. A timer
that rewrites your files is not something to discover.

The speech-to-text model (spec internal-engine "Transcribe speech on its own
connection and model") is a property of the operator's endpoint rather than of
Coffer, and writes on its own route, for the reason ``UpkeepUpdate`` records
below."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from coffer.application.audit_service import AuditService
from coffer.application.internal_engine_config_service import InternalEngineConfigService
from coffer.application.upkeep_clock import PASS_CLOCK, last_pass_at
from coffer.application.upkeep_schedule import DEFAULT_INTERVALS
from coffer.domain.internal_engine_config import (
    AGGREGATE,
    DISTIL,
    MEMORY_SYNC,
    GlobalInternalEngineConfig,
    UpkeepSetting,
)
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import (
    get_actor,
    get_audit_service,
    get_internal_engine_config_service,
)

#: The passes a client may name, in the order they run.
_PASSES = (AGGREGATE, DISTIL, MEMORY_SYNC)


# The request/response models live here rather than in ``schemas.py``, which is
# at its size ceiling — the same choice ``upkeep_routes`` makes, and it keeps a
# shape next to the one route that builds it.


class UpkeepSettingOut(BaseModel):
    """One unattended pass's switch and timer, as a surface needs to show them.

    ``interval_s`` is ``null`` while the operator has chosen none;
    ``default_interval_s`` is what runs in that case, reported so a settings
    page can name the default instead of showing a blank where a number
    belongs.
    """

    enabled: bool
    interval_s: int | None = None
    default_interval_s: int
    #: When this pass last finished on this machine, whoever asked for it
    #: (the timer, a button or the CLI); ``null`` if it never has (spec
    #: internal-engine "Report when each unattended pass last ran and runs next").
    last_pass_at: datetime | None = None
    #: When this machine's timer runs it next, against the interval as it
    #: stands now. ``null`` while the pass is switched off, while it is
    #: running, and on a daemon whose timer for it is not waiting.
    next_pass_at: datetime | None = None


class InternalEngineConfigOut(BaseModel):
    """Coffer's own operating settings: its unattended work and its speech-to-text."""

    updated_at: datetime | None = None
    #: Keyed by pass name (``aggregate`` / ``distil`` / ``memory_sync``).
    upkeep: dict[str, UpkeepSettingOut] = Field(default_factory=dict)
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


class UpkeepUpdate(BaseModel):
    """Change ONE unattended pass, leaving the others exactly as they stand.

    One pass at a time on purpose: a settings page toggles one row, and a body
    carrying both would make every toggle a chance to write back a stale
    copy of the other — on settings the operator may also be changing on
    another machine, since they converge through vault sync.

    Omitting a field leaves that half of the pass alone, so a switch and a
    timer can be changed independently.
    """

    pass_name: Literal["aggregate", "distil", "memory_sync"] = Field(alias="pass")
    enabled: bool | None = None
    interval_s: int | None = Field(default=None, ge=60)
    #: Explicitly return this pass to its own default interval. Needed because
    #: ``interval_s: null`` is indistinguishable from "not supplied" in JSON.
    use_default_interval: bool = False

    model_config = ConfigDict(populate_by_name=True)


router = APIRouter(
    prefix="/api/v1/internal-engine-config",
    tags=["internal-engine"],
    dependencies=[Depends(require_token)],
)


async def _to_out(cfg: GlobalInternalEngineConfig, audit: AuditService) -> InternalEngineConfigOut:
    """The settings row, with each pass's last and next run beside its switch.

    Every route answers with the whole shape, so a surface that reads the
    answer to its own write sees the same facts a fresh read would.
    """
    upkeep: dict[str, UpkeepSettingOut] = {}
    for name in _PASSES:
        setting = cfg.upkeep(name)
        default_s = int(DEFAULT_INTERVALS[name])
        interval = setting.interval_s or default_s
        upkeep[name] = UpkeepSettingOut(
            enabled=setting.enabled,
            interval_s=setting.interval_s,
            default_interval_s=default_s,
            last_pass_at=_utc(await last_pass_at(audit, name)),
            next_pass_at=PASS_CLOCK.next_due(name, interval) if setting.enabled else None,
        )
    return InternalEngineConfigOut(
        updated_at=cfg.updated_at,
        upkeep=upkeep,
        transcribe_model=cfg.transcribe_model,
    )


def _utc(moment: datetime | None) -> datetime | None:
    """An audit timestamp as an aware UTC instant (SQLite hands back naive ones)."""
    if moment is None or moment.tzinfo is not None:
        return moment
    return moment.replace(tzinfo=UTC)


@router.get("", response_model=InternalEngineConfigOut)
async def get_config(
    svc: InternalEngineConfigService = Depends(get_internal_engine_config_service),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
) -> InternalEngineConfigOut:
    return await _to_out(await svc.get(), audit)


@router.put("/upkeep", response_model=InternalEngineConfigOut)
async def update_upkeep(
    body: UpkeepUpdate,
    svc: InternalEngineConfigService = Depends(get_internal_engine_config_service),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> InternalEngineConfigOut:
    """Change one pass's switch or timer.

    Each half is left alone when the client does not send it, so a settings
    page can flip a switch without restating a timer it never looked at.
    """
    current = (await svc.get()).upkeep(body.pass_name)
    interval = (
        None
        if body.use_default_interval
        else (body.interval_s if body.interval_s is not None else current.interval_s)
    )
    setting = UpkeepSetting(
        enabled=current.enabled if body.enabled is None else body.enabled,
        interval_s=interval,
    )
    return await _to_out(await svc.set_upkeep(body.pass_name, setting, actor=actor), audit)


@router.put("/transcribe-model", response_model=InternalEngineConfigOut)
async def update_transcribe_model(
    body: TranscribeModelUpdate,
    svc: InternalEngineConfigService = Depends(get_internal_engine_config_service),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> InternalEngineConfigOut:
    """Choose the model Coffer transcribes speech with, or stop transcribing.

    Clearing it is an operating decision an operator may want — with no model
    the recording never leaves the machine — which is why it is expressed here
    rather than by deleting the connection that carries the endpoint.
    """
    return await _to_out(await svc.set_transcribe_model(body.model, actor=actor), audit)
