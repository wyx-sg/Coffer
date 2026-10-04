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
    """A connection's wire may be corrected, but not while an agent runs on it.

    The wire is not inert: an ``ollama`` connection covers no agent whatever its
    scope says (``application.provider.targets.scoped_targets``). Moving the
    wire of a connection an agent currently runs on would therefore leave the
    native config Coffer already wrote standing with nothing left that would
    ever take it off again.

    Refusing is the fix rather than de-projecting silently: the user asked to
    change a field, not to take their agents off a gateway. Maps to 409 — the
    request is well-formed and will succeed once no agent runs on the connection.
    """

    code = "PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE"

    def __init__(self, name: str, protocol: str, agent_types: list[str]) -> None:
        who = " and ".join(agent_types) or "those agents"
        super().__init__(
            f"connection {name!r} has agents running on it, so its wire format cannot change — "
            f"put those agents back on their built-in login first "
            f"(Change model on Model providers, for {who}), then edit the wire, "
            f"then switch them onto the connection again"
        )
        self.name = name
        self.protocol = protocol


class ProviderInternalOnly(CofferError):  # noqa: N818
    """An ``ollama`` connection cannot be switched on for an agent.

    It is internal-only: it has no key to project and reaches no agent whatever
    its scope says (``application.provider.targets.scoped_targets``), so no
    agent ever runs on it and switching one onto it writes nothing. Refused rather than
    answered with a switch that did not happen. Maps to 409.
    """

    code = "PROVIDER_INTERNAL_ONLY"

    def __init__(self, name: str) -> None:
        super().__init__(
            f"connection {name!r} uses the ollama protocol, which only Coffer's internal "
            f"engine uses — it cannot be switched on for an agent"
        )
        self.name = name


class ProviderDoesNotReachAgent(CofferError):  # noqa: N818
    """A connection cannot be switched onto an agent it does not reach.

    Reach is the connection's per-agent scope, narrowed by its ``enabled``
    switch. The ``reason`` says which it was. Maps to 409: the request is
    well-formed and succeeds once the connection is switched on, or the
    scope names the agent.
    """

    code = "PROVIDER_DOES_NOT_REACH_AGENT"

    def __init__(self, name: str, agent_type: str, reason: str) -> None:
        super().__init__(f"connection {name!r} cannot be switched on for {agent_type}: {reason}")
        self.name = name
        self.agent_type = agent_type


class ProviderInternalDefaultTaken(CofferError):  # noqa: N818
    """A write would flag a second connection as the internal-engine default.

    At most one connection carries ``internal_default`` (spec provider-switching
    "Keep at most one internal default connection"), and the one write that may
    move it is ``set_internal_default``, which clears the holder first. Any
    other write that sets the flag while a different connection holds it — the
    kind-agnostic resource PATCH or POST — is refused here rather than left to
    the vault's exclusive-flag rule. Maps to 409: the body is well-formed, and the
    dedicated route moves the flag.
    """

    code = "PROVIDER_INTERNAL_DEFAULT_TAKEN"

    def __init__(self, holder: str) -> None:
        super().__init__(
            f"connection {holder!r} is already Coffer's internal-engine default — "
            f"move the flag with Settings › General (Coffer's engine) "  # noqa: RUF001
            f"(POST /api/v1/providers/{{uid}}/internal-default) instead"
        )
        self.holder = holder


class ProviderTranscribeDefaultTaken(CofferError):  # noqa: N818
    """A write would flag a second connection as the speech-to-text default.

    The twin of :class:`ProviderInternalDefaultTaken`: at most one connection
    carries ``transcribe_default``, and the one write that may move it is
    ``set_transcribe_default``. Maps to 409.
    """

    code = "PROVIDER_TRANSCRIBE_DEFAULT_TAKEN"

    def __init__(self, holder: str) -> None:
        super().__init__(
            f"connection {holder!r} is already Coffer's speech-to-text default — "
            f"move the flag with Settings › General (Coffer's engine) "  # noqa: RUF001
            f"(POST /api/v1/providers/{{uid}}/transcribe-default) instead"
        )
        self.holder = holder
