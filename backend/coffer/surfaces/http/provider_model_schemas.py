"""Wire shapes for a provider's per-model facts: each model's price and its
context window, with where each came from (spec provider-switching "Resolve
each model's price from the provider, its API, or the bundled list",
"Resolve each provider model's context window"). Split from
``provider_schemas`` by size."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from coffer.domain.provider.model_window import WindowSource
from coffer.domain.usage.pricing import PriceSource


class ModelPricesIn(BaseModel):
    """The models whose price on this provider to resolve."""

    models: list[str] = Field(max_length=1000)


class ModelPriceOut(BaseModel):
    """One model's price on a provider and where it came from (spec
    provider-switching "Resolve each model's price from the provider, its API,
    or the bundled list"). USD per million tokens; ``source`` ``None`` means no
    price is known and every rate is ``None`` — shown as "—", never as zero.
    ``source_name`` names the provider whose API reported it (``provider``) or
    the price list's provider (``bundled``). ``tiered``: the rates shown are
    the base tier; past a threshold of input tokens the request pays more."""

    model: str
    source: PriceSource | None = None
    source_name: str | None = None
    input: float | None = None
    output: float | None = None
    cache_write_5m: float | None = None
    cache_write_1h: float | None = None
    cache_read: float | None = None
    tiered: bool = False
    #: For ``bundled``: the day the price list in use was taken from
    #: genai-prices — "Bundled · updated <date>".
    source_updated: date | None = None


class ModelPricesOut(BaseModel):
    prices: list[ModelPriceOut]
    #: The price list in use (``genai-prices@<commit or refresh day>…``).
    bundled_version: str


class ModelWindowOut(BaseModel):
    """One model's context window on a provider and where it came from (spec
    provider-switching "Resolve each provider model's context window").
    ``source`` ``None`` means no window is known and ``tokens`` is ``None``:
    nothing is written for it, nothing is guessed."""

    model: str
    tokens: int | None = None
    source: WindowSource | None = None


class ModelWindowsOut(BaseModel):
    windows: list[ModelWindowOut]
