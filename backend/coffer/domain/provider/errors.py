"""Provider-switching domain errors (spec 011). Surfaces map these to status."""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class ProviderCredentialSourceInvalid(CofferError):  # noqa: N818
    """A provider create must supply EXACTLY one of ``secret_value`` /
    ``credential_ref`` — not both, not neither. Maps to 422."""

    code = "PROVIDER_CREDENTIAL_SOURCE_INVALID"

    def __init__(self) -> None:
        super().__init__(
            "provide exactly one of 'secret_value' or 'credential_ref' (not both, not neither)"
        )


class NoActiveProvider(CofferError):  # noqa: N818
    """No active provider profile exists for the requested wire format. Maps
    to 404 — e.g. ``coffer provider key`` before any profile was activated."""

    code = "NO_ACTIVE_PROVIDER"

    def __init__(self, protocol: str) -> None:
        super().__init__(f"no active provider profile for protocol {protocol!r}")
        self.protocol = protocol
