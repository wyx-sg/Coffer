"""What one metered attempt cost — per model, per token category (ADR
usage-is-metered-at-the-proxy-and-subscriptions-show-only-official-quota).

A price is USD per million tokens for each DISJOINT category the proxy records
(:mod:`coffer.domain.usage.records`): uncached input, the 5-minute and 1-hour
cache writes, cache reads, and output (reasoning is a part of output, so it is
never priced twice). Server-tool web searches are priced per thousand
requests. Cache multipliers are per model — 0.1x input on most, lower on some —
so every category is a number of its own, never a ratio applied later. A price
may be TIERED: past a threshold of the request's total input tokens, every
token of the request is charged at that tier's rate (the "cliff" providers
publish).

Cost is an ESTIMATE computed once, at ingest, and stored with the label of the
price that produced it, so a later price never rewrites history. Where a price
comes from is :class:`PriceSource` — the user's own price on the provider, the
provider API's, the bundled list (:mod:`.bundled_prices`), or a local runtime,
which costs nothing — and a model none of them knows is UNPRICED: never priced
at zero.

:data:`BUNDLED_SNAPSHOT` is Coffer's own supplement to the bundled list: the
Anthropic first-party rates of models the list has not caught up with yet.

Pure: no I/O.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum

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
    #: ``(start, price)`` pairs, ascending: once a request's total input
    #: tokens pass ``start``, every token is charged at ``price``.
    tiers: tuple[tuple[int, ModelPrice], ...] = ()

    def at(self, total_input_tokens: int) -> ModelPrice:
        """The flat price a request with ``total_input_tokens`` pays."""
        chosen: ModelPrice = self
        for start, price in self.tiers:
            if total_input_tokens > start:
                chosen = price
        return replace(chosen, tiers=()) if chosen.tiers else chosen


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

    @property
    def total_input(self) -> int:
        """Every input token of the request, cached or not — what a tier's
        threshold is measured against."""
        return (
            self.input_tokens
            + self.cache_write_5m_tokens
            + self.cache_write_1h_tokens
            + self.cache_read_tokens
        )


def estimate_cost(tokens: TokenCounts, price: ModelPrice) -> float:
    """The estimated USD cost of ``tokens`` at ``price`` (its tier for the
    request's total input)."""
    price = price.at(tokens.total_input)
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


def model_candidates(model: str) -> list[str]:
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
        for candidate in model_candidates(model):
            price = self.prices.get(candidate)
            if price is not None:
                return price
        return None

    @property
    def label(self) -> str:
        """What a row priced from this snapshot stores as its price version."""
        return f"snapshot:{self.version}"


class PriceSource(StrEnum):
    """Where a model's price came from, in the order they are consulted."""

    #: The price the user set on the provider ("You set").
    USER = "user"
    #: The provider's own API reported it when its models were listed.
    PROVIDER = "provider"
    #: The price list shipped with this release.
    BUNDLED = "bundled"
    #: A model runtime on this machine: it costs nothing.
    LOCAL = "local"


@dataclass(frozen=True)
class ResolvedPrice:
    """A model's price, where it came from, and the label a costed row stores."""

    price: ModelPrice
    source: PriceSource
    #: ``override:<uid>`` / ``provider:<uid>`` / ``bundled:<version>`` / ``local``.
    label: str
    #: The provider that reported it, for ``PROVIDER``; the price list's
    #: provider (``Anthropic``, ``OpenAI``…) for ``BUNDLED``.
    source_name: str | None = None


#: Costs nothing: what a local runtime's models are priced at.
FREE = ModelPrice(input=0.0, output=0.0, cache_write_5m=0.0, cache_write_1h=0.0, cache_read=0.0)
#: The label of a row priced as a local runtime's.
LOCAL_LABEL = "local"


def override_label(connection_uid: str) -> str:
    """The price version of a row priced by a connection's own override."""
    return f"override:{connection_uid}"


def reported_label(connection_uid: str) -> str:
    """The price version of a row priced by what its provider's API reported."""
    return f"provider:{connection_uid}"


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

#: Anthropic first-party rates as of :data:`BUNDLED_SNAPSHOT_VERSION` — the
#: supplement consulted after the bundled list, for the models it lacks.
BUNDLED_SNAPSHOT = PriceSnapshot(
    version=BUNDLED_SNAPSHOT_VERSION,
    prices={
        "claude-fable-5-1": _anthropic(10, 50, cache_read=0.25),
        "claude-mythos-5-1": _anthropic(10, 50, cache_read=0.25),
        "claude-opus-5-5": _anthropic(4, 20, cache_read=0.20),
        "claude-sonnet-5-5": _anthropic(2, 10, cache_read=0.20),
    },
)


__all__ = [
    "BUNDLED_SNAPSHOT",
    "BUNDLED_SNAPSHOT_VERSION",
    "FREE",
    "LOCAL_LABEL",
    "ModelPrice",
    "PriceSnapshot",
    "PriceSource",
    "ResolvedPrice",
    "TokenCounts",
    "estimate_cost",
    "model_candidates",
    "override_label",
    "reported_label",
]
