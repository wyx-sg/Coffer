"""The state the daemon pushes to the model proxy over its control route.

The proxy holds no database and reads no secret store: everything it needs
— which local token belongs to which agent, and which upstream serves
each agent — arrives in one :class:`ProxyState`, pushed on spawn, on re-attach
and whenever a connection or an agent changes. Provider keys travel in it and
are held only in the proxy's memory; ``repr`` never shows them.

Tokens are carried as SHA-256 digests: the proxy compares the digest of what a
request presents, in constant time, and never needs the token itself.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from coffer.domain.usage.records import Wire


class UpstreamAuth(StrEnum):
    """How the proxy presents a connection's key upstream."""

    #: Anthropic wire: ``x-api-key`` and ``Authorization: Bearer`` — the pair
    #: Claude Code's own ``apiKeyHelper`` sends, which every Anthropic-shaped
    #: gateway already accepts.
    ANTHROPIC = "anthropic"
    #: OpenAI wire: ``Authorization: Bearer``.
    BEARER = "bearer"
    #: A keyless local runtime (Ollama, LM Studio, vLLM, llama-server).
    NONE = "none"


class ProxyMember(BaseModel):
    """The upstream a route sends its requests to: a connection's endpoint."""

    model_config = ConfigDict(extra="forbid")

    connection_uid: str
    #: The connection's name, for the usage record's ``member`` label.
    connection_name: str
    #: The endpoint root, without a trailing ``/v1``: the proxy appends the
    #: route's own path (``/v1/messages``, ``/v1/responses``, …).
    upstream_root: str
    auth: UpstreamAuth
    key: str | None = Field(default=None, repr=False)
    #: A model runtime on this machine: reached without the user's proxy, no key.
    local: bool = False


class ProxyRoute(BaseModel):
    """Where one agent's requests on one wire go: the connection it is on."""

    model_config = ConfigDict(extra="forbid")

    agent_uid: str
    wire: Wire
    member: ProxyMember
    #: The model ids the connection curates (empty: the whole catalogue, so no
    #: request is ever rewritten). A requested model outside this set is replaced
    #: by ``fallback_model`` (spec provider-switching, "Reach API-key and local
    #: connections through the local model proxy").
    served_models: list[str] = Field(default_factory=list)
    #: The agent's projected default model; None leaves every request untouched.
    fallback_model: str | None = None
    #: Anthropic wire only: tier (``haiku``/``sonnet``/``opus``/``fable``) -> the
    #: model Coffer projected for that tier into Claude Code. An unserved
    #: request naming a tier is replaced by its tier's model when the connection
    #: serves it, else by ``fallback_model``. Empty for Codex.
    tier_fallbacks: dict[str, str] = Field(default_factory=dict)


class ProxyAgent(BaseModel):
    """One managed agent and the digest of its local proxy token."""

    model_config = ConfigDict(extra="forbid")

    agent_uid: str
    agent_type: str
    token_sha256: str


class ProxyState(BaseModel):
    """Everything the proxy serves, replaced wholesale on every push."""

    model_config = ConfigDict(extra="forbid")

    revision: int = 0
    agents: list[ProxyAgent] = Field(default_factory=list)
    routes: list[ProxyRoute] = Field(default_factory=list)


def token_digest(token: str) -> str:
    """The SHA-256 hex digest the proxy compares a presented token against."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def upstream_root(base_url: str) -> str:
    """A connection's ``base_url`` as the root the proxy appends ``/v1/...`` to.

    Connections are stored the way each wire's clients spell them — Anthropic
    endpoints without ``/v1`` (``https://api.anthropic.com``), OpenAI-shaped ones
    with it (``https://api.openai.com/v1``, ``http://127.0.0.1:11434/v1``). One
    trailing ``/v1`` is dropped so both spellings reach the same place and one
    local runtime serving both wires is one connection.
    """
    root = base_url.strip().rstrip("/")
    if root.endswith("/v1"):
        root = root[: -len("/v1")].rstrip("/")
    return root


#: The port the proxy binds when ``daemon-config.json`` names none — fixed, so
#: the base URL written into the agents' files never moves on its own.
DEFAULT_PROXY_PORT = 38471

#: The path each wire's clients are pointed at, under the proxy's root.
WIRE_PATHS = {Wire.ANTHROPIC: "/anthropic", Wire.OPENAI: "/openai/v1"}


def proxy_root(port: int) -> str:
    """The proxy's loopback root on ``port``."""
    return f"http://127.0.0.1:{port}"


#: Secret-store refs holding the per-agent local proxy tokens:
#: ``proxy-token/<agent name>`` (``proxy-token/codex``). Machine-local — a
#: token unlocks this machine's loopback proxy and nothing else — so vault sync
#: never carries them.
PROXY_TOKEN_REF_PREFIX = "proxy-token/"

#: Header carrying the control token on the proxy's control routes.
CONTROL_TOKEN_HEADER = "x-coffer-proxy-control"

__all__ = [
    "CONTROL_TOKEN_HEADER",
    "DEFAULT_PROXY_PORT",
    "PROXY_TOKEN_REF_PREFIX",
    "WIRE_PATHS",
    "ProxyAgent",
    "ProxyMember",
    "ProxyRoute",
    "ProxyState",
    "UpstreamAuth",
    "proxy_root",
    "token_digest",
    "upstream_root",
]
