"""How ``coffer usage`` writes a cost (spec provider-switching "Price usage from
a bundled snapshot and per-connection prices"): a group nothing prices reads
as a dash, never as $0, and a partly priced one names what it leaves out."""

from __future__ import annotations

import pytest

from coffer.domain.usage.pricing import BUNDLED_SNAPSHOT
from coffer.surfaces.cli.usage_cmd import NO_PRICE, _cost


@pytest.mark.acceptance(
    spec="provider-switching", scenario="a model with no price reads as a dash, never zero"
)
def test_a_group_nothing_prices_reads_as_a_dash() -> None:
    # No OpenAI price is bundled: a Codex model is unpriced until its
    # connection carries a price.
    assert BUNDLED_SNAPSHOT.lookup("gpt-5.4") is None
    assert BUNDLED_SNAPSHOT.lookup("gpt-5.3-codex") is None
    assert _cost({"requests": 3, "unpriced_requests": 3, "estimated_cost_usd": 0.0}) == (
        f"{NO_PRICE} (3 unpriced)"
    )
    assert _cost({"requests": 4, "unpriced_requests": 1, "estimated_cost_usd": 0.5}) == (
        "~$0.5000 (+1 unpriced)"
    )
    assert _cost({"requests": 2, "unpriced_requests": 0, "estimated_cost_usd": 0.25}) == "~$0.2500"
