"""A stored key is probed only against the endpoint it was approved for.

The introspection routes take a ``secret_ref`` and a ``base_url`` from the
caller. Left free, that pair would decrypt any stored secret (an MCP token, a
channel token, a standalone secret) and send it to any URL (spec secret "Hold a
secret for a new destination until a person approves it"). So a ref is honoured
only when a saved provider connection cites it AND points at the same base URL,
and only once that connection's key is an approved destination
(``secret_gate.require_key``). A key typed into the dialog travels as an inline
``secret_value`` and never touches the store.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coffer.application.provider.secret_gate import require_key
from coffer.domain.errors import ConfigValidationError
from coffer.domain.provider.config import ProviderConfig

if TYPE_CHECKING:
    from coffer.application.provider.service import ProviderService


def _norm(url: str | None) -> str:
    return (url or "").strip().rstrip("/").lower()


async def authorize_stored_key(
    service: ProviderService,
    *,
    secret_ref: str | None,
    secret_value: str | None,
    base_url: str | None,
    default_base_url: str | None = None,
) -> None:
    """Refuse a stored ``secret_ref`` that is not a saved connection's key for ``base_url``.

    ``default_base_url`` is the protocol's own endpoint, used when the caller
    names none. A call with an inline value, or with no ref, has nothing stored
    to guard.
    """
    if secret_value or not secret_ref:
        return
    wanted = _norm(base_url or default_base_url)
    for row in await service.list():
        cfg = ProviderConfig.model_validate(row.config)
        if cfg.secret_ref == secret_ref and _norm(cfg.base_url) == wanted:
            await require_key(service, row.uid, row.name, cfg)
            return
    raise ConfigValidationError(
        "a stored key can be tried only against the endpoint of the saved connection "
        "that holds it; paste the key to try it elsewhere"
    )
