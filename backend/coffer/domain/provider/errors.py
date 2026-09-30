"""Provider-switching domain errors (spec provider-switching). Surfaces map these to status."""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class ProviderSecretSourceInvalid(CofferError):  # noqa: N818
    """A provider create must supply EXACTLY one of ``secret_value`` /
    ``secret_ref`` — not both, not neither. Maps to 422."""

    code = "PROVIDER_SECRET_SOURCE_INVALID"

    def __init__(self) -> None:
        super().__init__(
            "provide exactly one of 'secret_value' or 'secret_ref' (not both, not neither)"
        )


class ProviderProtocolLockedWhileActive(CofferError):  # noqa: N818
    """A connection's wire may be corrected, but not while it is switched on.

    The wire is not inert: an ``ollama`` connection covers no agent whatever its
    scope says (``application.provider.targets.scoped_targets``). Moving the
    wire of a connection that is currently projected would therefore leave the
    native config Coffer already wrote standing with nothing left that would
    ever take it off again.

    Refusing is the fix rather than de-projecting silently: the user asked to
    change a field, not to take their agents off a gateway. Maps to 409 — the
    request is well-formed and will succeed once the connection is off.
    """

    code = "PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE"

    def __init__(self, name: str, protocol: str, agent_types: list[str]) -> None:
        how = " and ".join(f"`coffer provider builtin {t}`" for t in agent_types) or (
            "`coffer provider builtin <agent_type>`"
        )
        super().__init__(
            f"connection {name!r} is switched on, so its wire format cannot change — "
            f"put its agents back on their built-in login first "
            f"({how}), then edit the wire, "
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
    """A connection has no secret to hand the local model proxy — raised
    by the service's key lookup, which the proxy's membership check treats as
    "not a member". Maps to 404."""

    code = "NO_ACTIVE_PROVIDER"

    def __init__(self, protocol: str) -> None:
        super().__init__(f"no active provider profile for protocol {protocol!r}")
        self.protocol = protocol


class ProviderInternalDefaultTaken(CofferError):  # noqa: N818
    """A write would flag a second connection as the internal-engine default.

    At most one connection carries ``internal_default`` (spec provider-switching
    "Keep at most one internal default connection"), and the one write that may
    move it is ``set_internal_default``, which clears the holder first. Any
    other write that sets the flag while a different connection holds it — the
    kind-agnostic resource PATCH or POST — is refused here rather than left to
    the database's unique index. Maps to 409: the body is well-formed, and the
    dedicated route moves the flag.
    """

    code = "PROVIDER_INTERNAL_DEFAULT_TAKEN"

    def __init__(self, holder: str) -> None:
        super().__init__(
            f"connection {holder!r} is already Coffer's internal-engine default — "
            f"move the flag with `coffer config set engine.provider <name>` "
            f"(POST /api/v1/providers/{{uid}}/internal-default) instead"
        )
        self.holder = holder
