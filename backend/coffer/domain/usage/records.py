"""One usage record per upstream attempt — the wire between the model proxy
and the daemon (ADR usage-is-metered-at-the-proxy-and-subscriptions-show-only-
official-quota).

The proxy never opens a database. It appends these records, one JSON object
per line, to spool files under ``~/.coffer/proxy-usage/``; the daemon, the only
writer of the database, ingests completed files and deletes each only after its
rows are committed. A file being written ends in :data:`PART_SUFFIX`; the
writer renames it to :data:`SPOOL_SUFFIX` once it will not grow any more, so a
reader only ever sees whole files.

Token counts are stored in DISJOINT categories, so they add up without double
counting: ``input_tokens`` is the UNCACHED input (Anthropic's ``input_tokens``
as sent; OpenAI's ``input_tokens`` minus ``cached_tokens``), the two cache-write
buckets, ``cache_read_tokens``, and ``output_tokens`` — of which
``reasoning_tokens`` is a part, not an addition. A stream cut before its
terminal usage event has ``usage_known = False`` and every count ``None``:
recorded, never dropped, never guessed.

Nothing here is ever a body, a prompt, a completion or a credential.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

#: Directory under ``~/.coffer`` the proxy spools usage into.
SPOOL_DIRNAME = "proxy-usage"
#: A completed spool file — safe to ingest and then delete.
SPOOL_SUFFIX = ".jsonl"
#: A spool file still being appended to; never read.
PART_SUFFIX = ".jsonl.part"
#: Environment override of the spool directory (tests, relocated homes).
SPOOL_DIR_ENV = "COFFER_PROXY_SPOOL_DIR"

#: The ``source`` column value of every row the proxy produces. A later source
#: (a transcript importer) coexists through ``source`` + ``dedupe_key``.
PROXY_SOURCE = "proxy"

RECORD_SCHEMA = 1


class Wire(StrEnum):
    """The protocol a proxy route speaks — the same wire in and out."""

    ANTHROPIC = "anthropic"  # Anthropic Messages (Claude Code)
    OPENAI = "openai"  # OpenAI Responses (Codex)


class Outcome(StrEnum):
    """How one upstream attempt ended."""

    COMPLETED = "completed"  # terminal event / full body relayed
    ERROR_EVENT = "error_event"  # an ``event: error`` / ``response.failed`` in the stream
    TRUNCATED = "truncated"  # the upstream stream ended before its terminal event
    CLIENT_CANCEL = "client_cancel"  # the agent went away mid-response
    UPSTREAM_ERROR = "upstream_error"  # a non-2xx status relayed (or failed over)
    CONNECT_ERROR = "connect_error"  # DNS / TCP / TLS / first-byte timeout


class UsageRecord(BaseModel):
    """What one upstream attempt cost, and who made it."""

    model_config = ConfigDict(extra="ignore")

    schema_version: int = RECORD_SCHEMA
    source: str = PROXY_SOURCE
    #: The upstream's request id (``request-id`` / ``x-request-id``) when it
    #: answered, else ``attempt:<attempt_id>`` — an ingest that repeats after a
    #: crash writes nothing twice.
    dedupe_key: str
    attempt_id: str
    started_at: datetime
    #: The agent, from the per-agent local token — never self-reported.
    agent_uid: str | None = None
    agent_type: str | None = None
    #: Where the agent sends them: ``x-claude-code-session-id`` /
    #: ``x-claude-code-request-class``, Codex ``session_id``.
    session_id: str | None = None
    request_class: str | None = None
    connection_uid: str | None = None
    #: A human label of the member that served the attempt (the connection's
    #: name) — never a key.
    member: str | None = None
    wire: Wire
    endpoint: str
    #: The ``model`` the request asked for.
    model: str | None = None
    stream: bool = False
    status: int | None = None
    outcome: Outcome
    #: This attempt failed before the first content byte and the request moved
    #: to another member.
    failed_over: bool = False
    ttft_ms: int | None = None
    duration_ms: int = 0
    usage_known: bool = False
    input_tokens: int | None = None
    cache_write_5m_tokens: int | None = None
    cache_write_1h_tokens: int | None = None
    cache_read_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    web_search_requests: int | None = None
    #: Anthropic ``usage.speed`` / ``usage.inference_geo`` modifiers, as sent.
    speed: str | None = None
    inference_geo: str | None = None
    upstream_request_id: str | None = Field(default=None)


__all__ = [
    "PART_SUFFIX",
    "PROXY_SOURCE",
    "RECORD_SCHEMA",
    "SPOOL_DIRNAME",
    "SPOOL_DIR_ENV",
    "SPOOL_SUFFIX",
    "Outcome",
    "UsageRecord",
    "Wire",
]
