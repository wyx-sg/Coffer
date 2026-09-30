"""Provider order is fallback priority; each provider's switch; prices with
their source (spec provider-switching "Order providers, and fail over in that
order", "Resolve each model's price from the provider, its API, or the
bundled list")."""

from __future__ import annotations

import pytest

from coffer.domain.usage.pricing import ModelPrice
from coffer.infrastructure.provider.reported_prices import shared_store
from tests.integration.surfaces.http.test_provider_routes import (
    _agent_dir,
    _anthropic_body,
    _app,
    _client,
    _new,
    _register_agent,
    _route_keys,
)

MODEL = "claude-sonnet-4-6"


def _offering(name: str, secret: str) -> dict:
    return _anthropic_body(name, secret_value=secret, models=[{"id": MODEL}])


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="fallbacks are tried in the Model providers list order",
)
def test_fallbacks_follow_the_list_order(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 62300)
    with _client(app) as c:
        cc = _register_agent(c, agent_type="claude_code", config_dir=_agent_dir(tmp_path))
        primary = _new(c, _offering("a-primary", "sk-a"))
        zed = _new(c, _offering("z-second", "sk-z"))
        mid = _new(c, _offering("m-third", "sk-m"))
        assert c.post(f"/api/v1/providers/{primary}/activate").status_code == 200
        # Nobody has placed them: alphabetical, as before.
        assert [u for u, _ in _route_keys(c)[cc]] == [primary, mid, zed]

        r = c.put("/api/v1/providers/order", json={"uids": [zed, primary, mid]})
        assert r.status_code == 200, r.text
        assert [p["uid"] for p in r.json()["providers"]] == [zed, primary, mid]
        assert [p["uid"] for p in c.get("/api/v1/providers").json()["providers"]] == [
            zed,
            primary,
            mid,
        ]
        # The agent's own provider is still first; the rest follow the list.
        assert [u for u, _ in _route_keys(c)[cc]] == [primary, zed, mid]

        route = c.get(f"/api/v1/proxy/routes/{cc}", params={"model": MODEL}).json()
        assert route["primary"]["connection_uid"] == primary
        assert [f["connection_uid"] for f in route["fallbacks"]] == [zed, mid]
        other = c.get(f"/api/v1/proxy/routes/{cc}", params={"model": "not-offered"}).json()
        assert other["fallbacks"] == []

        audit = c.get("/api/v1/audit", params={"event_type": "provider_reordered"}).json()
        assert audit["entries"][0]["details"]["order"] == ["z-second", "a-primary", "m-third"]


def test_an_order_that_misses_a_provider_is_refused(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 62310)
    with _client(app) as c:
        a = _new(c, _offering("a", "sk-a"))
        _new(c, _offering("b", "sk-b"))
        assert c.put("/api/v1/providers/order", json={"uids": [a]}).status_code == 422
        assert c.put("/api/v1/providers/order", json={"uids": [a, a]}).status_code == 422


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a provider switched off as a fallback is never failed over to",
)
def test_a_provider_switched_off_as_fallback_is_left_out(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 62320)
    with _client(app) as c:
        cc = _register_agent(c, agent_type="claude_code", config_dir=_agent_dir(tmp_path))
        primary = _new(c, _offering("a-primary", "sk-a"))
        spare = _new(c, _offering("b-spare", "sk-b"))
        assert c.get(f"/api/v1/providers/{spare}").json()["fallback"] is True
        assert c.post(f"/api/v1/providers/{primary}/activate").status_code == 200
        assert [u for u, _ in _route_keys(c)[cc]] == [primary, spare]

        r = c.patch(f"/api/v1/providers/{spare}", json={"fallback": False})
        assert r.status_code == 200 and r.json()["fallback"] is False
        assert [u for u, _ in _route_keys(c)[cc]] == [primary]
        route = c.get(f"/api/v1/proxy/routes/{cc}", params={"model": MODEL}).json()
        assert route["fallbacks"] == []

        hint = c.get(f"/api/v1/proxy/tokens/{cc}/hint").json()
        token = c.get(f"/api/v1/proxy/tokens/{cc}").json()["token"]
        assert hint["last4"] == token[-4:]


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
