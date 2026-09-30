"""`coffer provider order` and `coffer provider price` (spec provider-switching
"Order providers, and fail over in that order", "Resolve each model's price
from the provider, its API, or the bundled list").

``order`` places providers in the Model providers list — which is also the
order the model proxy tries fallbacks in. ``price`` shows each model's price
and where it came from, and sets or resets the price the user records on a
provider ("You set"), which wins over every other source.
"""

from __future__ import annotations

import json
from typing import Any

import typer

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._kind_verbs import verbose_of
from coffer.surfaces.cli._resolve import resolve_ref

#: How each source reads, as the web UI shows it.
SOURCE_LABELS = {"user": "You set", "bundled": "Bundled", "local": "Local · no cost"}
NO_PRICE = "—"
_NAMES = typer.Argument(..., metavar="NAME...", help="Providers, first to last")


def _rate(value: float | None) -> str:
    return NO_PRICE if value is None else f"${value:,.2f}"


def source_label(row: dict[str, Any]) -> str:
    """``You set`` / ``From <provider>`` / ``Bundled`` / ``Local · no cost`` / ``—``."""
    source = row.get("source")
    if source == "provider":
        return f"From {row.get('source_name') or 'the provider'}"
    return SOURCE_LABELS.get(str(source), NO_PRICE)


def order(
    ctx: typer.Context,
    names: list[str] = _NAMES,
) -> None:
    """Put providers in this order; the rest keep theirs, after them.

    The order is fallback priority: when an agent's model is offered by more
    than one enabled provider, the proxy tries the agent's own provider first,
    then the others in this order, before the first byte of the answer.
    """
    verbose = verbose_of(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        first = [resolve_ref(c, "provider", n, verbose=verbose)["uid"] for n in names]
        r = c.get("/providers")
        _cli_client.check(r, verbose=verbose)
        rest = [p["uid"] for p in r.json()["providers"] if p["uid"] not in first]
        r = c.put("/providers/order", json={"uids": list(dict.fromkeys(first)) + rest})
        if r.status_code == 422:
            typer.echo(f"invalid order: {r.text}", err=True)
            raise typer.Exit(6)
        _cli_client.check(r, verbose=verbose)
    for i, p in enumerate(r.json()["providers"], start=1):
        typer.echo(f"{i}. {p['name']}")


def price(
    ctx: typer.Context,
    name: str = typer.Argument(..., metavar="NAME", help="Provider name or uid"),
    model: str | None = typer.Argument(None, metavar="[MODEL]", help="Model to set or reset"),
    input_: float | None = typer.Option(None, "--input", help="USD per 1M input tokens"),
    output: float | None = typer.Option(None, "--output", help="USD per 1M output tokens"),
    cache_read: float | None = typer.Option(None, "--cache-read", help="USD per 1M cache reads"),
    cache_write: float | None = typer.Option(
        None, "--cache-write", help="USD per 1M cache writes (5-minute)"
    ),
    reset: bool = typer.Option(False, "--reset", help="Remove the price you set on MODEL"),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output"),
) -> None:
    """Show each model's price on a provider and its source, or set one.

    Without MODEL: every model the provider offers, with its price per 1M
    tokens (input · output) and where it came from — You set, From <provider>
    (its own API reported it), Bundled (the price list shipped with this
    release) or — when nothing prices it. With MODEL and --input/--output:
    record your own price, which wins over every other source. --reset
    removes it.
    """
    verbose = verbose_of(ctx)
    setting = input_ is not None or output is not None or reset
    if setting and model is None:
        typer.echo("name the MODEL to set a price on", err=True)
        raise typer.Exit(6)
    if setting and not reset and (input_ is None or output is None):
        typer.echo("--input and --output are both required to set a price", err=True)
        raise typer.Exit(6)
    c, _info = _cli_client.client_or_exit()
    with c:
        provider = resolve_ref(c, "provider", name, verbose=verbose)
        uid = provider["uid"]
        current = c.get(f"/providers/{uid}")
        _cli_client.check(current, verbose=verbose)
        curated: list[dict[str, Any]] = current.json()["models"]
        if setting:
            assert model is not None
            _set(c, uid, curated, model, reset, input_, output, cache_read, cache_write, verbose)
            curated = c.get(f"/providers/{uid}").json()["models"]
        ids = [model] if model else [m["id"] for m in curated]
        if not ids:
            typer.echo(f"{provider['name']} offers every model its endpoint lists; name a MODEL")
            return
        r = c.post(f"/providers/{uid}/prices", json={"models": ids})
        _cli_client.check(r, verbose=verbose)
    rows = r.json()["prices"]
    if as_json:
        typer.echo(json.dumps(rows, indent=2))
        return
    width = max(len(row["model"]) for row in rows)
    for row in rows:
        rates = (
            NO_PRICE
            if row.get("source") is None
            else f"{_rate(row['input'])} · {_rate(row['output'])} / 1M"
        )
        typer.echo(f"{row['model']:<{width}}  {rates:<24} {source_label(row)}")


def _set(
    c: Any,
    uid: str,
    curated: list[dict[str, Any]],
    model: str,
    reset: bool,
    input_: float | None,
    output: float | None,
    cache_read: float | None,
    cache_write: float | None,
    verbose: bool,
) -> None:
    if not any(m["id"] == model for m in curated):
        if reset:
            return
        if not curated:
            # An empty curated set means "every model the endpoint lists";
            # adding one entry would quietly narrow it to that one model.
            typer.echo(
                "this provider offers every model its endpoint lists; choose which models it "
                "offers first (the provider's Models section in the Coffer app), then set a price",
                err=True,
            )
            raise typer.Exit(6)
        typer.echo(f"{model!r} is not one of this provider's models", err=True)
        raise typer.Exit(6)
    value = None
    if not reset:
        value = {"input": input_, "output": output}
        if cache_read is not None:
            value["cache_read"] = cache_read
        if cache_write is not None:
            value["cache_write_5m"] = cache_write
    models = [{**m, "price": value} if m["id"] == model else m for m in curated]
    r = c.patch(f"/providers/{uid}", json={"models": models})
    if r.status_code in (400, 422):
        typer.echo(f"invalid price: {r.text}", err=True)
        raise typer.Exit(6)
    _cli_client.check(r, verbose=verbose)


__all__ = ["order", "price", "source_label"]
