"""The price list shipped with each release (spec provider-switching "Resolve
each model's price from the provider, its API, or the bundled list").

The data is pydantic/genai-prices (MIT): the snapshot ``make refresh-prices``
ships, or the copy the daemon refreshes daily; a lookup never touches the
network. It is
PROVIDER-SCOPED: the same model id can cost differently at two providers, so a
price is looked up at the provider the connection points at — found from its
base URL (each provider's ``api_pattern``) — and only an endpoint no provider
claims (a company gateway, a relay) falls back to the provider whose model
names the id matches (``claude…`` → Anthropic, ``gpt-…`` → OpenAI), the way
genai-prices itself does. A provider that resells another's models
(``fallback_model_providers``) looks there one step.

A model may carry HISTORICAL prices (the last whose ``start_date`` has passed
wins), time-of-day prices, and TIERED prices (a threshold of total input
tokens past which every token is charged at the tier's rate); all three are
read. The categories map onto Coffer's disjoint ones: ``input_mtok`` →
uncached input, ``cache_write_mtok`` → the 5-minute cache write,
``cache_write_1h_mtok`` → the 1-hour one, ``cache_read_mtok`` → cache reads,
``output_mtok`` → output, ``web_searches_kcount`` → web search. Where the list
gives no 1-hour rate for an Anthropic model, it is twice the input rate, the
vendor's published rule.

After the list, Coffer's own :data:`~coffer.domain.usage.pricing.BUNDLED_SNAPSHOT`
supplies Anthropic models the list has not caught up with yet. Both are
"Bundled".

Pure: parses a document handed to it; the file is read by
``infrastructure.usage.bundled_prices``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from typing import Any

from coffer.domain.usage.pricing import (
    BUNDLED_SNAPSHOT,
    ModelPrice,
    PriceSnapshot,
    model_candidates,
)

Matcher = Callable[[str], bool]

_COMPACT_DATE = re.compile(r"(-)(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?=-|:|$)")


def compile_match(logic: Mapping[str, Any] | None) -> Matcher:
    """A genai-prices match clause as a predicate over a lower-cased id."""
    if not logic:
        return lambda _text: False
    if "or" in logic:
        parts = [compile_match(c) for c in logic["or"]]
        return lambda text: any(p(text) for p in parts)
    if "and" in logic:
        parts = [compile_match(c) for c in logic["and"]]
        return lambda text: all(p(text) for p in parts)
    if "equals" in logic:
        value = str(logic["equals"]).lower()
        return lambda text: text == value
    if "starts_with" in logic:
        value = str(logic["starts_with"]).lower()
        return lambda text: text.startswith(value)
    if "ends_with" in logic:
        value = str(logic["ends_with"]).lower()
        return lambda text: text.endswith(value)
    if "contains" in logic:
        value = str(logic["contains"]).lower()
        return lambda text: value in text
    if "regex" in logic:
        pattern = re.compile(str(logic["regex"]))
        return lambda text: bool(pattern.search(text))
    return lambda _text: False


def _normalize_compact_date(model: str) -> str:
    """``gpt-5.2-20251211`` → ``gpt-5.2-2025-12-11`` (the list's spelling)."""

    def fix(m: re.Match[str]) -> str:
        try:
            date(int(m.group(2)), int(m.group(3)), int(m.group(4)))
        except ValueError:
            return m.group(0)
        return f"{m.group(1)}{m.group(2)}-{m.group(3)}-{m.group(4)}"

    return _COMPACT_DATE.sub(fix, model)


def _base_and_tiers(value: Any) -> tuple[float | None, list[tuple[int, float]]]:
    if value is None:
        return None, []
    if isinstance(value, Mapping):
        tiers = [(int(t["start"]), float(t["price"])) for t in value.get("tiers", [])]
        return float(value["base"]), sorted(tiers)
    return float(value), []


def to_model_price(prices: Mapping[str, Any], *, anthropic: bool) -> ModelPrice | None:
    """One genai-prices ``ModelPrice`` mapping in Coffer's categories, or
    ``None`` when it prices no token (an image-only or per-request model)."""
    fields = {
        "input": _base_and_tiers(prices.get("input_mtok")),
        "output": _base_and_tiers(prices.get("output_mtok")),
        "cache_write_5m": _base_and_tiers(prices.get("cache_write_mtok")),
        "cache_read": _base_and_tiers(prices.get("cache_read_mtok")),
        "cache_write_1h": _base_and_tiers(prices.get("cache_write_1h_mtok")),
    }
    if fields["input"][0] is None and fields["output"][0] is None:
        return None
    starts = sorted({start for _base, tiers in fields.values() for start, _ in tiers})
    searches = prices.get("web_searches_kcount")
    web_search = (
        float(searches) if isinstance(searches, int | float) else (10.0 if anthropic else None)
    )

    def at(start: int | None) -> ModelPrice:
        values: dict[str, float | None] = {}
        for name, (base, tiers) in fields.items():
            chosen = base
            for tier_start, price in tiers:
                if start is not None and tier_start <= start:
                    chosen = price
            values[name] = chosen
        inp = values["input"] if values["input"] is not None else 0.0
        one_hour = values["cache_write_1h"]
        if one_hour is None and anthropic:
            one_hour = inp * 2
        return ModelPrice(
            input=inp,
            output=values["output"] if values["output"] is not None else 0.0,
            cache_write_5m=values["cache_write_5m"],
            cache_write_1h=one_hour,
            cache_read=values["cache_read"],
            web_search=web_search,
        )

    base = at(None)
    if not starts:
        return base
    return ModelPrice(
        input=base.input,
        output=base.output,
        cache_write_5m=base.cache_write_5m,
        cache_write_1h=base.cache_write_1h,
        cache_read=base.cache_read,
        web_search=base.web_search,
        tiers=tuple((s, at(s)) for s in starts),
    )


def _active(constraint: Mapping[str, Any] | None, at: datetime) -> bool:
    if not constraint:
        return True
    moment = at.astimezone(UTC) if at.tzinfo else at.replace(tzinfo=UTC)
    if "start_date" in constraint:
        return moment.date() >= date.fromisoformat(str(constraint["start_date"]))
    if "start_time" in constraint and "end_time" in constraint:
        start = time.fromisoformat(str(constraint["start_time"]).rstrip("Z"))
        end = time.fromisoformat(str(constraint["end_time"]).rstrip("Z"))
        now = moment.time()
        if end < start:
            return now >= start or now < end
        return start <= now < end
    return True


@dataclass(frozen=True)
class _Model:
    id: str
    match: Matcher
    prices: Any  # a mapping, or a list of {constraint?, prices}

    def prices_at(self, at: datetime) -> Mapping[str, Any]:
        if isinstance(self.prices, Mapping):
            return self.prices
        for conditional in reversed(self.prices):
            if _active(conditional.get("constraint"), at):
                return dict(conditional["prices"])
        return dict(self.prices[0]["prices"])


@dataclass(frozen=True)
class _Provider:
    id: str
    name: str
    api_pattern: re.Pattern[str]
    model_match: Matcher | None
    fallbacks: tuple[str, ...]
    models: tuple[_Model, ...] = field(default_factory=tuple)

    def find(self, model: str) -> _Model | None:
        return next((m for m in self.models if m.match(model)), None)


@dataclass(frozen=True)
class BundledMatch:
    """A bundled price and the list provider it was found under."""

    price: ModelPrice
    provider_name: str


class BundledPrices:
    """The release's price list, looked up by model at a provider."""

    def __init__(
        self,
        providers: Sequence[_Provider],
        *,
        version: str,
        supplement: PriceSnapshot | None = BUNDLED_SNAPSHOT,
        updated: date | None = None,
        refreshed: bool = False,
    ) -> None:
        self._providers = list(providers)
        self._by_id = {p.id: p for p in self._providers}
        self.version = version
        self._supplement = supplement
        #: The day the list's data was taken from genai-prices.
        self.updated = updated
        #: Fetched by the daemon's daily refresh, not shipped in the build.
        self.refreshed = refreshed

    @classmethod
    def from_document(
        cls, document: Mapping[str, Any], *, supplement: PriceSnapshot | None = BUNDLED_SNAPSHOT
    ) -> BundledPrices:
        """Parse the document ``make refresh-prices`` writes (``commit`` and
        ``fetched``), or the cache the daily refresh writes (``fetched_at``)."""
        providers = [
            _Provider(
                id=str(p["id"]),
                name=str(p.get("name") or p["id"]),
                api_pattern=re.compile(str(p.get("api_pattern") or r"(?!)")),
                model_match=compile_match(p["model_match"]) if p.get("model_match") else None,
                fallbacks=tuple(p.get("fallback_model_providers") or ()),
                models=tuple(
                    _Model(id=str(m["id"]), match=compile_match(m.get("match")), prices=m["prices"])
                    for m in p.get("models", [])
                    if m.get("prices") is not None
                ),
            )
            for p in document.get("providers", [])
        ]
        refreshed = "fetched_at" in document
        updated = _day(document.get("fetched_at") or document.get("fetched"))
        tag = (
            f"refreshed-{updated.isoformat() if updated else 'unknown'}"
            if refreshed
            else str(document.get("commit") or "unknown")[:12]
        )
        version = f"genai-prices@{tag}"
        if supplement is not None:
            version += f"+coffer@{supplement.version}"
        return cls(
            providers, version=version, supplement=supplement, updated=updated, refreshed=refreshed
        )

    @classmethod
    def empty(cls) -> BundledPrices:
        """Only Coffer's own supplement — when the list file is missing."""
        return cls([], version=f"coffer@{BUNDLED_SNAPSHOT.version}")

    @property
    def label(self) -> str:
        """What a row priced from this list stores as its price version."""
        return f"bundled:{self.version}"

    def _provider_for(self, base_url: str | None, model: str) -> _Provider | None:
        if base_url:
            url = base_url.strip()
            for provider in self._providers:
                if provider.api_pattern.match(url):
                    return provider
        for provider in self._providers:
            if provider.model_match is not None and provider.model_match(model):
                return provider
        return None

    def _find(self, provider: _Provider, model: str) -> tuple[_Provider, _Model] | None:
        hit = provider.find(model)
        if hit is not None:
            return provider, hit
        for fallback_id in provider.fallbacks:
            other = self._by_id.get(fallback_id)
            if other is not None and (hit := other.find(model)) is not None:
                return other, hit
        return None

    def lookup(
        self, model: str | None, *, base_url: str | None = None, at: datetime | None = None
    ) -> BundledMatch | None:
        """The bundled price of ``model`` at the provider ``base_url`` names,
        as of ``at`` (now when omitted); ``None`` when neither the list nor the
        supplement knows it.

        The list wins when it names the model by its own id. When it only
        reaches it through a broader pattern (``claude-opus-5`` also matches
        ``claude-opus-5-5``) and Coffer's supplement names the id exactly, the
        supplement wins: it is there for models the list has not caught up with.
        """
        if not model:
            return None
        moment = at or datetime.now(UTC)
        supplement = self._supplement.lookup(model) if self._supplement is not None else None
        for candidate in dict.fromkeys(
            c.lower()
            for raw in model_candidates(model)
            for c in (raw, _normalize_compact_date(raw))
        ):
            provider = self._provider_for(base_url, candidate)
            found = self._find(provider, candidate) if provider is not None else None
            if found is None:
                continue
            owner, entry = found
            if supplement is not None and entry.id.lower() != candidate:
                break
            price = to_model_price(entry.prices_at(moment), anthropic=owner.id == "anthropic")
            if price is not None:
                return BundledMatch(price=price, provider_name=owner.name)
        if supplement is not None:
            return BundledMatch(price=supplement, provider_name="Anthropic")
        return None


def _day(value: Any) -> date | None:
    """``2026-09-30`` or an ISO timestamp, as a day; ``None`` when unreadable."""
    if not value:
        return None
    text = str(value)
    try:
        return datetime.fromisoformat(text).date() if "T" in text else date.fromisoformat(text)
    except ValueError:
        return None


def validate_payload(payload: Any) -> list[dict[str, Any]]:
    """The provider array genai-prices publishes, checked before it may be
    cached: a non-empty list of providers with ids and models, among them
    Anthropic and OpenAI, that parses. Raises ``ValueError`` otherwise."""
    if not isinstance(payload, list) or not payload:
        raise ValueError("expected a non-empty provider array")
    ids = set()
    for provider in payload:
        if not isinstance(provider, Mapping) or not isinstance(provider.get("id"), str):
            raise ValueError("a provider has no id")
        if not isinstance(provider.get("models"), list):
            raise ValueError(f"provider {provider['id']} has no model list")
        ids.add(provider["id"])
    if not {"anthropic", "openai"} <= ids:
        raise ValueError("the list is missing Anthropic or OpenAI")
    BundledPrices.from_document({"providers": payload}, supplement=None)
    return [dict(p) for p in payload]


__all__ = [
    "BundledMatch",
    "BundledPrices",
    "compile_match",
    "to_model_price",
    "validate_payload",
]
