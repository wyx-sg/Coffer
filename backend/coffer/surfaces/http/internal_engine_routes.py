# backend/coffer/surfaces/http/internal_engine_routes.py
"""/api/v1/internal-engine-config — Coffer's own operating settings.

Two things live on one singleton because they are one question with two halves:
WHICH MODEL Coffer thinks with, and WHAT IT DOES unattended. The model comes
from here while the endpoint and key come from the ``internal_default``
connection (spec provider-switching amendment 2026-06-22b); the unattended work
is the three passes Coffer runs on a timer — aggregation (spec memory FR-007),
organise (spec memory FR-017) and curate (spec knowledge FR-021) — each with a
switch and an interval the operator can see and change.

That last part is why the surface exists at all: two of the three had no switch
anywhere, the third's could only be changed by hand-editing a synced settings
document, and all three intervals were constants compiled into the workers. A
timer that rewrites your files is not something to discover."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from coffer.application.internal_engine_config_service import InternalEngineConfigService
from coffer.application.upkeep_schedule import DEFAULT_INTERVALS
from coffer.domain.errors import ConfigValidationError
from coffer.domain.internal_engine_config import (
    AGGREGATE,
    CURATE,
    ORGANISE,
    GlobalInternalEngineConfig,
    UpkeepSetting,
)
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor, get_internal_engine_config_service

#: The passes a client may name, in the order they run.
_PASSES = (AGGREGATE, ORGANISE, CURATE)


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


class InternalEngineConfigOut(BaseModel):
    """Coffer's own operating settings: its model, and its unattended work."""

    model: str | None = None
    updated_at: datetime | None = None
    #: Keyed by pass name (``aggregate`` / ``organise`` / ``tidy``).
    upkeep: dict[str, UpkeepSettingOut] = Field(default_factory=dict)


class InternalEngineConfigUpdate(BaseModel):
    """Set the internal-engine model; ``null``/empty clears it."""

    model: str | None = None


class UpkeepUpdate(BaseModel):
    """Change ONE unattended pass, leaving the others exactly as they stand.

    One pass at a time on purpose: a settings page toggles one row, and a body
    carrying all three would make every toggle a chance to write back a stale
    copy of the other two — on settings the operator may also be changing on
    another machine, since they converge through vault sync.

    Omitting a field leaves that half of the pass alone, so a switch and a
    timer can be changed independently.
    """

    pass_name: str = Field(alias="pass")
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


def _to_out(cfg: GlobalInternalEngineConfig) -> InternalEngineConfigOut:
    return InternalEngineConfigOut(
        model=cfg.model,
        updated_at=cfg.updated_at,
        upkeep={
            name: UpkeepSettingOut(
                enabled=cfg.upkeep(name).enabled,
                interval_s=cfg.upkeep(name).interval_s,
                default_interval_s=int(DEFAULT_INTERVALS[name]),
            )
            for name in _PASSES
        },
    )


@router.get("", response_model=InternalEngineConfigOut)
async def get_config(
    svc: InternalEngineConfigService = Depends(get_internal_engine_config_service),  # noqa: B008
) -> InternalEngineConfigOut:
    return _to_out(await svc.get())


@router.put("", response_model=InternalEngineConfigOut)
async def update_config(
    body: InternalEngineConfigUpdate,
    svc: InternalEngineConfigService = Depends(get_internal_engine_config_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> InternalEngineConfigOut:
    return _to_out(await svc.update(model=body.model, actor=actor))


@router.put("/upkeep", response_model=InternalEngineConfigOut)
async def update_upkeep(
    body: UpkeepUpdate,
    svc: InternalEngineConfigService = Depends(get_internal_engine_config_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> InternalEngineConfigOut:
    """Change one pass's switch or timer.

    Each half is left alone when the client does not send it, so a settings
    page can flip a switch without restating a timer it never looked at.
    """
    if body.pass_name not in _PASSES:
        raise ConfigValidationError(
            f"unknown upkeep pass '{body.pass_name}' (known: {', '.join(_PASSES)})"
        )
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
    return _to_out(await svc.set_upkeep(body.pass_name, setting, actor=actor))
