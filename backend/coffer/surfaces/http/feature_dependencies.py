"""The feature service's FastAPI seams, and the gate a feature's routes carry.

The service is built in ``create_app`` rather than in the lifespan: the
unauthenticated ``/daemon/status`` reports ``channel`` and ``features``, and it
must answer during startup, before the lifespan has wired anything. It is kept
on ``app.state.feature_service`` and published through the ``set_*``/``get_*``
pair here, like the other kind-agnostic services in ``dependencies``.
"""

from __future__ import annotations

from collections.abc import Callable

from coffer import build_channel
from coffer.application.features import FeatureService
from coffer.domain.features import FeatureDisabled, feature_keys, get_feature
from coffer.infrastructure.daemon import config as daemon_config
from coffer.infrastructure.daemon.feature_settings import DaemonConfigFeatureSettings


def build_feature_service() -> FeatureService:
    """This build's channel, this machine's settings, this process's pins."""
    return FeatureService(
        channel=build_channel.CHANNEL,
        settings=DaemonConfigFeatureSettings(),
        pins=daemon_config.read_feature_pins(feature_keys()),
    )


_feature_service: FeatureService | None = None


def set_feature_service(svc: FeatureService) -> None:
    """Called by the composition root (``create_app``)."""
    global _feature_service
    _feature_service = svc


def get_feature_service() -> FeatureService:
    """FastAPI Depends() target."""
    if _feature_service is None:
        raise RuntimeError("feature service not initialised")
    return _feature_service


def get_feature_service_optional() -> FeatureService | None:
    """The service if published, else ``None`` — for ``/daemon/status``, which
    also answers on an app assembled without ``create_app``."""
    return _feature_service


def require_feature(key: str) -> Callable[[], None]:
    """A dependency that answers 404 ``FEATURE_DISABLED`` while ``key`` is off.

    Put on a router (``dependencies=[Depends(require_feature("knowledge"))]``):
    the routes stay registered, so the OpenAPI document does not change with
    the switch, and the state is read per request, so a switch takes effect
    without a restart (spec experimental-features "Close every surface of a
    switched-off feature").
    """
    get_feature(key)  # an unregistered key is a wiring mistake: fail at import

    def _gate() -> None:
        if not get_feature_service().is_enabled(key):
            raise FeatureDisabled(key)

    return _gate
