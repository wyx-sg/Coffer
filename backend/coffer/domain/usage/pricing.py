"""What one metered attempt cost — per model, per token category (ADR
usage-is-metered-at-the-proxy-and-subscriptions-show-only-official-quota).

A price is USD per million tokens for each DISJOINT category the proxy records
(:mod:`coffer.domain.usage.records`): uncached input, the 5-minute and 1-hour
cache writes, cache reads, and output (reasoning is a part of output, so it is
never priced twice). Server-tool web searches are priced per thousand
requests. Cache multipliers are per model — 0.1x input on most, lower on some —
so every category is a number of its own, never a ratio applied later.

Cost is an ESTIMATE computed once, at ingest, and stored with the name of the
snapshot or override that produced it, so a later table never rewrites history.
A model this snapshot does not know is UNPRICED — :meth:`PriceSnapshot.lookup`
returns ``None`` and the caller flags the row — never priced at zero.

The bundled snapshot carries Anthropic first-party rates only. No OpenAI prices
are bundled: there is no verified source for them here, so an OpenAI (Codex)
model stays unpriced until the user sets a price on the connection it goes
through (the connection override, which also covers relays and resellers that
price differently from the vendor).

Pure: no I/O.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from coffer.domain.usage.records import UsageRecord

_PER_MTOK = 1_000_000
_PER_1K = 1_000


@dataclass(frozen=True)
class ModelPrice:
    """USD per million tokens of each category; ``web_search`` per 1k requests.

    A cache price left ``None`` is charged at the ``input`` rate — the
    conservative choice for an override that names only input and output, so
    an estimate errs high rather than silently low. ``web_search`` left
    ``None`` adds nothing.
    """

    input: float
    output: float
    cache_write_5m: float | None = None
    cache_write_1h: float | None = None
    cache_read: float | None = None
    web_search: float | None = None


@dataclass(frozen=True)
class TokenCounts:
    """The disjoint token categories of one attempt (a ``None`` count is 0)."""

    input_tokens: int = 0
    cache_write_5m_tokens: int = 0
    cache_write_1h_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0
    web_search_requests: int = 0

    @classmethod
    def of(cls, record: UsageRecord) -> TokenCounts:
        return cls(
            input_tokens=record.input_tokens or 0,
            cache_write_5m_tokens=record.cache_write_5m_tokens or 0,
            cache_write_1h_tokens=record.cache_write_1h_tokens or 0,
            cache_read_tokens=record.cache_read_tokens or 0,
            output_tokens=record.output_tokens or 0,
            web_search_requests=record.web_search_requests or 0,
        )


def estimate_cost(tokens: TokenCounts, price: ModelPrice) -> float:
    """The estimated USD cost of ``tokens`` at ``price``."""
    fallback = price.input
    per_mtok = (
        tokens.input_tokens * price.input
        + tokens.cache_write_5m_tokens * _or(price.cache_write_5m, fallback)
        + tokens.cache_write_1h_tokens * _or(price.cache_write_1h, fallback)
        + tokens.cache_read_tokens * _or(price.cache_read, fallback)
        + tokens.output_tokens * price.output
    )
    search = tokens.web_search_requests * (price.web_search or 0.0) / _PER_1K
    return per_mtok / _PER_MTOK + search


def _or(value: float | None, fallback: float) -> float:
    return fallback if value is None else value


#: Cloud-provider prefixes a model id may carry: ``anthropic.`` (Bedrock) and a
#: region-routed ``us.anthropic.`` / ``eu.anthropic.`` / ``apac.anthropic.`` /
#: ``global.anthropic.``.
_PROVIDER_PREFIX = re.compile(r"^(?:[a-z]+\.)?anthropic\.")
#: Claude Code's long-context marker on a model id, e.g. ``claude-opus-4-6[1m]``.
_CONTEXT_SUFFIX = re.compile(r"\[1m\]$", re.IGNORECASE)
#: Bedrock's ``-v1:0`` version and a Vertex ``@20250514`` / dated ``-20251001``
#: snapshot suffix — the same model, priced the same.
_VERSION_SUFFIX = re.compile(r"(?:-v\d+(?::\d+)?|@\d{8}|-\d{8})$")


def _candidates(model: str) -> list[str]:
    """``model`` as sent, then with prefix and suffixes stripped one by one."""
    out = [model]
    bare = _PROVIDER_PREFIX.sub("", _CONTEXT_SUFFIX.sub("", model.strip()))
    out.append(bare)
    while True:
        shorter = _VERSION_SUFFIX.sub("", bare)
        if shorter == bare:
            return out
        bare = shorter
        out.append(bare)


@dataclass(frozen=True)
class PriceSnapshot:
    """A pinned, versioned price table: ``prices`` keyed by model id."""

    version: str
    prices: Mapping[str, ModelPrice] = field(default_factory=dict)

    def lookup(self, model: str | None) -> ModelPrice | None:
        """The price of ``model``, or ``None`` when it is unpriced.

        Tries the id exactly, then without a cloud prefix (``anthropic.``,
        ``us.anthropic.`` …) and a trailing ``[1m]``, then without a version or
        date suffix.
        """
        if not model:
            return None
        for candidate in _candidates(model):
            price = self.prices.get(candidate)
            if price is not None:
                return price
        return None

    @property
    def label(self) -> str:
        """What a row priced from this snapshot stores as its price version."""
        return f"snapshot:{self.version}"


def override_label(connection_uid: str) -> str:
    """The price version of a row priced by a connection's own override."""
    return f"override:{connection_uid}"


def _anthropic(input_: float, output: float, *, cache_read: float | None = None) -> ModelPrice:
    """Anthropic's standard category rates: a 5-minute cache write is 1.25x
    input, a 1-hour write 2x, a cache read 0.1x unless the model says
    otherwise; web search is $10 per 1k."""
    return ModelPrice(
        input=input_,
        output=output,
        cache_write_5m=input_ * 1.25,
        cache_write_1h=input_ * 2,
        cache_read=round(input_ * 0.1, 6) if cache_read is None else cache_read,
        web_search=10.0,
    )


BUNDLED_SNAPSHOT_VERSION = "2026-09-25"

#: Anthropic first-party rates as of :data:`BUNDLED_SNAPSHOT_VERSION`.
BUNDLED_SNAPSHOT = PriceSnapshot(
    version=BUNDLED_SNAPSHOT_VERSION,
    prices={
        "claude-fable-5-1": _anthropic(10, 50, cache_read=0.25),
        "claude-fable-5": _anthropic(10, 50),
        "claude-mythos-5-1": _anthropic(10, 50, cache_read=0.25),
        "claude-opus-5-5": _anthropic(4, 20, cache_read=0.20),
        "claude-opus-5": _anthropic(5, 25),
        "claude-opus-4-8": _anthropic(5, 25),
        "claude-opus-4-7": _anthropic(5, 25),
        "claude-opus-4-6": _anthropic(5, 25),
        "claude-sonnet-5-5": _anthropic(2, 10, cache_read=0.20),
        "claude-sonnet-5": _anthropic(2, 10),
        "claude-sonnet-4-6": _anthropic(3, 15),
        "claude-haiku-4-5": _anthropic(1, 5),
    },
)


__all__ = [
    "BUNDLED_SNAPSHOT",
    "BUNDLED_SNAPSHOT_VERSION",
    "ModelPrice",
    "PriceSnapshot",
    "TokenCounts",
    "estimate_cost",
    "override_label",
]
