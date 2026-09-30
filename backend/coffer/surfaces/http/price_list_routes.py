"""/api/v1/providers/price-list — the model price list and its daily refresh
(spec provider-switching "Refresh the bundled price list in the background").

GET says which list pricing reads now (the bundled snapshot or the daily
refresh's cache, whichever is fresher), when its data was taken from
genai-prices, and the refresh's state; PUT turns the refresh on or off on
this machine. Registered before the provider router, whose ``/{uid}`` would
otherwise answer ``price-list`` as a uid.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, status

from coffer.infrastructure.usage.price_refresh import (
    PriceListSource,
    read_refresh_setting,
    refresh_pinned_off,
    write_refresh_setting,
)
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.provider_schemas import PriceListIn, PriceListOut

router = APIRouter(
    prefix="/api/v1/providers/price-list",
    tags=["providers"],
    dependencies=[Depends(require_token)],
)

_source: PriceListSource | None = None


def set_price_list_source(source: PriceListSource | None) -> None:
    """Called by the composition root once on startup."""
    global _source
    _source = source


def get_price_list_source() -> PriceListSource:
    if _source is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="price list not wired"
        )
    return _source


def _out(source: PriceListSource) -> PriceListOut:
    current = source.current()
    return PriceListOut(
        version=current.version,
        updated=current.updated,
        origin="refreshed" if current.refreshed else "bundled",
        refresh=read_refresh_setting(),
        pinned_off=refresh_pinned_off(),
        last_attempt_at=source.status.last_attempt_at,
        last_error=source.status.last_error,
    )


@router.get("", response_model=PriceListOut)
async def get_price_list(
    source: PriceListSource = Depends(get_price_list_source),  # noqa: B008
) -> PriceListOut:
    """The price list in use and its refresh."""
    return _out(source)


@router.put("", response_model=PriceListOut)
async def put_price_list(
    body: PriceListIn,
    source: PriceListSource = Depends(get_price_list_source),  # noqa: B008
) -> PriceListOut:
    """Turn the daily refresh on or off on this machine. Nothing is fetched now;
    the next tick of the refresh reads the setting."""
    await asyncio.to_thread(write_refresh_setting, body.refresh)
    return _out(source)


__all__ = ["get_price_list_source", "router", "set_price_list_source"]
