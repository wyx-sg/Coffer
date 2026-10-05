"""Provider-switching domain errors (spec provider-switching). Surfaces map these to status."""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class ProviderSecretSourceInvalid(CofferError):  # noqa: N818
    """A provider create must supply EXACTLY one of ``secret_value`` /
    ``secret_ref`` — not both, not neither. A PATCH that sends both, or sends
    either to a connection with no key, is refused with it too. Maps to 422."""

    code = "PROVIDER_SECRET_SOURCE_INVALID"

    def __init__(self) -> None:
        super().__init__(
            "provide exactly one of 'secret_value' or 'secret_ref' (not both, not neither)"
        )


class ProviderProtocolLockedWhileActive(CofferError):  # noqa: N818
    """A connection's wire may be corrected, but not while an agent runs on it.

    The wire is not inert: an anthropic connection moved to another wire
    changes what Coffer projects into the agent's native config. Moving the
    wire of a connection an agent currently runs on would therefore leave the
    native config Coffer already wrote standing, speaking the old wire.

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


class ProviderProtocolRetired(CofferError):  # noqa: N818
    """The ``ollama`` protocol is no longer offered.

    Nothing consumes an ``ollama``-protocol connection: it holds no key to
    project, so no agent runs on it. Creating one, moving a connection onto
    it, or switching an agent onto a stored one is refused rather than
    answered with something that does nothing. A local Ollama runtime is
    added on its ``anthropic`` or ``openai`` wire instead. Maps to 422.
    """

    code = "PROVIDER_PROTOCOL_RETIRED"

    def __init__(self, name: str | None = None) -> None:
        who = f"connection {name!r} uses" if name else "the"
        super().__init__(
            f"{who} ollama protocol, which is no longer offered — "
            f"add a local Ollama runtime on its anthropic or openai wire instead"
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


class ProviderTranscribeDefaultTaken(CofferError):  # noqa: N818
    """A write would flag a second connection as the speech-to-text default.

    At most one connection carries ``transcribe_default`` (spec
    provider-switching "Keep an independent speech-to-text default"),
    and the one write that may move it is ``set_transcribe_default``. Maps to
    409.
    """

    code = "PROVIDER_TRANSCRIBE_DEFAULT_TAKEN"

    def __init__(self, holder: str) -> None:
        super().__init__(
            f"connection {holder!r} is already Coffer's speech-to-text default — "
            f"move the flag with Settings › General (Coffer's engine) "  # noqa: RUF001
            f"(POST /api/v1/providers/{{uid}}/transcribe-default) instead"
        )
        self.holder = holder
