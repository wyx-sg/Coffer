"""Provider-switching domain errors (spec provider-switching). Surfaces map these to status."""

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


class ProviderProtocolLockedWhileActive(CofferError):  # noqa: N818
    """A connection's wire may be corrected, but not while it is switched on.

    The wire is not inert: an ``ollama`` connection covers no agent whatever its
    scope says (``application.provider.targets.scoped_targets``), and
    ``use-builtin <wire>`` finds the agent to revert through the wire→agent map
    in ``application.provider.service``. Moving the wire of a connection that is
    currently projected would therefore leave the native config Coffer already
    wrote standing with nothing left that would ever take it off again.

    Refusing is the fix rather than de-projecting silently: the user asked to
    change a field, not to take their agents off a gateway. Maps to 409 — the
    request is well-formed and will succeed once the connection is off.
    """

    code = "PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE"

    def __init__(self, name: str, protocol: str) -> None:
        super().__init__(
            f"connection {name!r} is switched on, so its wire format cannot change — "
            f"put its agents back on their built-in login first "
            f"(`coffer provider use-builtin {protocol}`), then edit the wire, "
            f"then switch the connection on again"
        )
        self.name = name
        self.protocol = protocol


class ProviderInternalOnly(CofferError):  # noqa: N818
    """An ``ollama`` connection cannot be switched on for an agent.

    It is internal-only: it has no key to project and reaches no agent whatever
    its scope says (``application.provider.targets.scoped_targets``), so it is
    never ``is_active`` and activating it writes nothing. Refused rather than
    answered with a switch that did not happen. Maps to 409.
    """

    code = "PROVIDER_INTERNAL_ONLY"

    def __init__(self, name: str) -> None:
        super().__init__(
            f"connection {name!r} uses the ollama protocol, which only Coffer's internal "
            f"engine uses — it cannot be switched on for an agent"
        )
        self.name = name


class NoActiveProvider(CofferError):  # noqa: N818
    """No active provider profile exists for the requested wire format. Maps
    to 404 — e.g. ``coffer provider key`` before any profile was activated."""

    code = "NO_ACTIVE_PROVIDER"

    def __init__(self, protocol: str) -> None:
        super().__init__(f"no active provider profile for protocol {protocol!r}")
        self.protocol = protocol
