"""Which member a request goes to, and which members are resting.

Failover is deliberately narrow (ADR api-key-providers-are-reached-through-a-
separate-local-model-proxy, "Failover"):

- **Eligibility.** The route's first member — the agent's active connection —
  is always a candidate. A later member is a candidate only when it is not a
  local runtime and its ``models`` list names the requested model: failover
  never changes the model, and an empty list is NOT read as "any model" here,
  because a guess would be a silent model substitution. A LOCAL primary never
  fails over at all — a request the user meant for a model on their own
  machine must not quietly leave it for a cloud endpoint.
- **Health.** A 429 cools its member for ``retry-after`` (or a short default);
  a 401/403 disables it until a state push changes that member; a 5xx, 529,
  connect error, first-byte timeout, mid-stream error or truncation cools it
  briefly. There is no success counter to climb back: a cooldown just ends.
- **Affinity.** ``(agent_uid, session_id)`` sticks to the member that last
  served it until that member fails, which keeps the upstream prompt cache
  warm — moving a session between keys costs a full cache write.
- **One pass.** A request tries each candidate at most once, in order; the
  agents already retry, and retrying the same key is how a retry storm starts.
  If every candidate is resting, the primary is still tried: the upstream's own
  answer is more useful to the agent than a synthetic refusal.

Health is keyed by ``connection_uid``, remembered with a fingerprint of the
member's key, root and auth mode, so a push that changes any of them (the user
fixed the key) wipes that member's record.
"""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

from coffer.domain.model_proxy.state import ProxyMember, ProxyRoute

#: How long a member rests after a transient failure.
SHORT_COOLDOWN_SECONDS = 30.0
#: The longest a ``retry-after`` may bench a member — past this the value is
#: more likely a quota reset than a rate limit, and the user will see the
#: upstream's own 429 on the primary anyway.
MAX_RETRY_AFTER_SECONDS = 3600.0
#: How many sessions' affinities are remembered (least recently used dropped).
AFFINITY_CAP = 4096


def fingerprint(member: ProxyMember) -> str:
    """What identifies "the same member" across state pushes. Hashed, so the
    key never sits in the health table in plain form."""
    raw = "\0".join((member.upstream_root, member.auth.value, member.key or ""))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_retry_after(value: str | None, *, now: float | None = None) -> float | None:
    """Seconds from a ``retry-after`` header — integer seconds or an HTTP-date."""
    if not value:
        return None
    text = value.strip()
    try:
        return max(0.0, float(text))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    current = time.time() if now is None else now
    return max(0.0, when.timestamp() - current)


@dataclass
class _Health:
    fingerprint: str
    resting_until: float = 0.0
    disabled: bool = False


class MemberBook:
    """Health and affinity for every member the proxy currently knows."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._health: dict[str, _Health] = {}
        self._affinity: OrderedDict[tuple[str, str], str] = OrderedDict()

    # --- state -------------------------------------------------------------

    def reconcile(self, members: Iterable[ProxyMember]) -> None:
        """Adopt a pushed state: a member whose fingerprint changed starts clean
        (a re-entered key re-enables it); members no longer present are forgotten."""
        seen: dict[str, str] = {m.connection_uid: fingerprint(m) for m in members}
        for uid in list(self._health):
            if uid not in seen or self._health[uid].fingerprint != seen[uid]:
                del self._health[uid]
        for key in [k for k, uid in self._affinity.items() if uid not in seen]:
            del self._affinity[key]

    def _entry(self, member: ProxyMember) -> _Health:
        fp = fingerprint(member)
        entry = self._health.get(member.connection_uid)
        if entry is None or entry.fingerprint != fp:
            entry = _Health(fingerprint=fp)
            self._health[member.connection_uid] = entry
        return entry

    def available(self, member: ProxyMember) -> bool:
        entry = self._health.get(member.connection_uid)
        if entry is None or entry.fingerprint != fingerprint(member):
            return True
        return not entry.disabled and entry.resting_until <= self._clock()

    def disabled(self, member: ProxyMember) -> bool:
        entry = self._health.get(member.connection_uid)
        return bool(entry and entry.disabled and entry.fingerprint == fingerprint(member))

    # --- outcomes ------------------------------------------------------------

    def _forget_affinity(self, connection_uid: str) -> None:
        for key in [k for k, uid in self._affinity.items() if uid == connection_uid]:
            del self._affinity[key]

    def rest(self, member: ProxyMember, seconds: float = SHORT_COOLDOWN_SECONDS) -> None:
        """Bench ``member`` for ``seconds`` (a transient failure)."""
        entry = self._entry(member)
        entry.resting_until = max(entry.resting_until, self._clock() + seconds)
        self._forget_affinity(member.connection_uid)

    def rate_limited(self, member: ProxyMember, retry_after: float | None) -> None:
        seconds = SHORT_COOLDOWN_SECONDS if retry_after is None else retry_after
        self.rest(member, min(seconds, MAX_RETRY_AFTER_SECONDS))

    def auth_failed(self, member: ProxyMember) -> None:
        """401/403: the key is wrong until the user changes it."""
        self._entry(member).disabled = True
        self._forget_affinity(member.connection_uid)

    def served(self, member: ProxyMember, agent_uid: str, session_id: str | None) -> None:
        """Pin the session to the member that just answered it."""
        if not session_id:
            return
        key = (agent_uid, session_id)
        self._affinity[key] = member.connection_uid
        self._affinity.move_to_end(key)
        while len(self._affinity) > AFFINITY_CAP:
            self._affinity.popitem(last=False)

    # --- planning ------------------------------------------------------------

    def candidates(
        self, route: ProxyRoute, model: str | None, session_id: str | None
    ) -> list[ProxyMember]:
        """The members to try for one request, in order, each at most once."""
        if not route.members:
            return []
        primary = route.members[0]
        eligible = [primary]
        if not primary.local and model:
            seen = {primary.connection_uid}
            for member in route.members[1:]:
                if member.local or model not in member.models or member.connection_uid in seen:
                    continue
                seen.add(member.connection_uid)
                eligible.append(member)
        ready = [m for m in eligible if self.available(m)]
        if not ready:
            return [primary]
        sticky = self._affinity.get((route.agent_uid, session_id)) if session_id else None
        if sticky is not None:
            ready.sort(key=lambda m: m.connection_uid != sticky)
        return ready


__all__ = [
    "AFFINITY_CAP",
    "MAX_RETRY_AFTER_SECONDS",
    "SHORT_COOLDOWN_SECONDS",
    "MemberBook",
    "fingerprint",
    "parse_retry_after",
]
