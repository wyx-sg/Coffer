"""/api/v1/daemon/features — list and switch the experimental features.

Kept apart from ``daemon_routes`` for the file-size cap; same prefix, same tag.
Both routes carry the token: only ``/daemon/status`` is a probe.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from coffer.application.features import FeatureService, FeatureState
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.daemon_schemas import FeatureListOut, FeatureOut, FeatureSetIn
from coffer.surfaces.http.feature_dependencies import get_feature_service

router = APIRouter(
    prefix="/api/v1/daemon/features",
    tags=["daemon"],
    dependencies=[Depends(require_token)],
)


def _out(state: FeatureState) -> FeatureOut:
    return FeatureOut(key=state.key, enabled=state.enabled, source=state.source)


@router.get("", response_model=FeatureListOut)
async def list_features(
    features: FeatureService = Depends(get_feature_service),  # noqa: B008
) -> FeatureListOut:
    return FeatureListOut(channel=features.channel, features=[_out(s) for s in features.list()])


@router.put("/{key}", response_model=FeatureOut)
async def set_feature(
    key: str,
    body: FeatureSetIn,
    features: FeatureService = Depends(get_feature_service),  # noqa: B008
) -> FeatureOut:
    """Switch one feature on this machine, at once and without a restart.

    An unknown key answers 404 ``FEATURE_UNKNOWN``, a pinned one 409
    ``FEATURE_PINNED``; the setting is in ``daemon-config.json`` before this
    answers.
    """
    return _out(await features.set(key, body.enabled))
