"""The providers list reads by name; prices come with their source (spec
provider-switching "Resolve each model's price from the provider, its API, or
the bundled list")."""

from __future__ import annotations

import pytest

from coffer.domain.usage.pricing import ModelPrice
from coffer.infrastructure.provider.reported_prices import shared_store
from tests.integration.surfaces.http.test_provider_routes import (
    _anthropic_body,
    _app,
    _client,
    _new,
)

MODEL = "claude-sonnet-4-6"


def test_the_list_is_by_name_whatever_the_case(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 62300)
    with _client(app) as c:
        for name in ("zed", "Alpha", "mid"):
            _new(c, _anthropic_body(name, secret_value=f"sk-{name}", models=[{"id": MODEL}]))
        names = [p["name"] for p in c.get("/api/v1/providers").json()["providers"]]
        assert names == ["Alpha", "mid", "zed"]


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="each price names where it came from",
)
def test_each_price_names_its_source(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 62330)
    with _client(app) as c:
        uid = _new(
            c,
            {
                "name": "router",
                "protocol": "openai",
                "base_url": "https://openrouter.ai/api/v1",
                "secret_value": "sk-or",
                "models": [
                    {"id": "mine", "price": {"input": 1.5, "output": 12}},
                    {"id": "reported"},
                ],
            },
        )
        # What the provider's API reported at its last listing.
        shared_store().put(
            "https://openrouter.ai/api", {"reported": ModelPrice(input=0.5, output=2.0)}
        )
        r = c.post(
            f"/api/v1/providers/{uid}/prices",
            json={"models": ["mine", "reported", "anthropic/claude-sonnet-4.5", "nobody-knows"]},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        rows = {p["model"]: p for p in body["prices"]}
        assert (rows["mine"]["source"], rows["mine"]["input"]) == ("user", 1.5)
        assert (rows["reported"]["source"], rows["reported"]["source_name"]) == (
            "provider",
            "router",
        )
        assert rows["anthropic/claude-sonnet-4.5"]["source"] == "bundled"
        assert rows["anthropic/claude-sonnet-4.5"]["source_name"] == "OpenRouter"
        assert rows["nobody-knows"]["source"] is None
        assert rows["nobody-knows"]["input"] is None
        assert body["bundled_version"].startswith("genai-prices@")
        assert rows["anthropic/claude-sonnet-4.5"]["source_updated"]

        # The price list and its refresh: on by default, off on request.
        doc = c.get("/api/v1/providers/price-list").json()
        assert (doc["origin"], doc["refresh"], doc["pinned_off"]) == ("bundled", True, True)
        assert doc["updated"]
        off = c.put("/api/v1/providers/price-list", json={"refresh": False}).json()
        assert off["refresh"] is False
        assert c.get("/api/v1/providers/price-list").json()["refresh"] is False
