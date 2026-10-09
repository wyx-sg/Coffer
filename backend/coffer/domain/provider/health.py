"""Whether a connection's endpoint answers, and with what key verdict.

One verdict per connection, kept by this machine (spec provider-switching
"Know each connection's health without opening it"). Two kinds of evidence
write it, and both reduce to the same three states:

- a **check** — the model-list call the detail page, its Test, the periodic
  sweep and the re-check after an edit all make. It never spends a token;
- a **request** — what the local model proxy saw while relaying an agent's
  real call (its usage record): a 401/403 means the key is refused, a
  connection that never opened means the endpoint is unreachable, a relayed
  answer means it works. Anything else (a 429, a 5xx, a cut stream) says
  nothing about the connection and changes nothing.

A refused key is told apart from a dead endpoint by the status the failure
carries (401/403) or, for a listing whose error is only text, by the words
the vendors' SDKs use for it.

Pure: no I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from coffer.domain.usage.records import Outcome, UsageRecord

#: The longest failure text kept with a verdict; the rest is cut.
MESSAGE_MAX = 200

_AUTH_RE = re.compile(
    r"\b(401|403)\b|unauthori[sz]ed|forbidden|invalid[\s_-]*(api[\s_-]*)?key|authentication",
    re.IGNORECASE,
)


class HealthStatus(StrEnum):
    REACHABLE = "reachable"
    KEY_REJECTED = "key_rejected"
    UNREACHABLE = "unreachable"


class HealthSource(StrEnum):
    #: A model-list call Coffer made itself.
    CHECK = "check"
    #: An agent's real request through the local model proxy.
    REQUEST = "request"


@dataclass(frozen=True)
class ProviderHealth:
    status: HealthStatus
    checked_at: datetime
    source: HealthSource
    #: Why it failed, cut to :data:`MESSAGE_MAX`; empty when reachable.
    message: str = ""
    #: When this status was first seen without a break; ``None`` reads as ``checked_at``.
    since: datetime | None = None

    @property
    def started(self) -> datetime:
        return self.since or self.checked_at

    @property
    def failing(self) -> bool:
        return self.status is not HealthStatus.REACHABLE


def clip(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= MESSAGE_MAX else text[: MESSAGE_MAX - 1] + "…"


def is_auth_failure(message: str) -> bool:
    """Whether a failure text names a refused key (401/403 or its wording)."""
    return bool(message) and _AUTH_RE.search(message) is not None


def from_listing(
    *, reachable: bool, message: str, at: datetime, source: HealthSource = HealthSource.CHECK
) -> ProviderHealth:
    """The verdict of one model-list call (``ModelList.reachable`` + its message).

    An endpoint that answered with no models is reachable: it answered.
    """
    if reachable:
        return ProviderHealth(HealthStatus.REACHABLE, at, source)
    status = HealthStatus.KEY_REJECTED if is_auth_failure(message) else HealthStatus.UNREACHABLE
    return ProviderHealth(status, at, source, clip(message) or "the endpoint did not answer")


def from_request(record: UsageRecord) -> ProviderHealth | None:
    """What one relayed request says about its connection, or ``None`` when it
    says nothing (no connection, a cancel, a rate limit, a server error)."""
    if record.connection_uid is None:
        return None
    at = record.started_at
    if record.status in (401, 403):
        return ProviderHealth(
            HealthStatus.KEY_REJECTED,
            at,
            HealthSource.REQUEST,
            f"the endpoint answered HTTP {record.status} to an agent's request",
        )
    if record.outcome is Outcome.CONNECT_ERROR:
        return ProviderHealth(
            HealthStatus.UNREACHABLE,
            at,
            HealthSource.REQUEST,
            "an agent's request could not reach the endpoint",
        )
    if record.outcome is Outcome.COMPLETED and record.status is not None and record.status < 300:
        return ProviderHealth(HealthStatus.REACHABLE, at, HealthSource.REQUEST)
    return None


def latest_per_connection(records: list[UsageRecord]) -> dict[str, ProviderHealth]:
    """The newest verdict each connection's records carry."""
    out: dict[str, ProviderHealth] = {}
    for record in records:
        verdict = from_request(record)
        if verdict is None or record.connection_uid is None:
            continue
        seen = out.get(record.connection_uid)
        if seen is None or verdict.checked_at >= seen.checked_at:
            out[record.connection_uid] = verdict
    return out


__all__ = [
    "MESSAGE_MAX",
    "HealthSource",
    "HealthStatus",
    "ProviderHealth",
    "clip",
    "from_listing",
    "from_request",
    "is_auth_failure",
    "latest_per_connection",
]
