"""Which origins the CORS allowlist resolves to, per environment.

`test_cors.py` covers the preflight behaviour once an allowlist is in place;
this pins the allowlist itself. The daemon-served browser path is same-origin
and needs nothing. The desktop shell is the one host that genuinely does: its
page origin is the WebView's own while its API calls go to loopback, so every
call preflights.

What keeps that entry honest is that the token, not the origin, is the
boundary — so these tests pin both halves: that the shell origin is present,
and that being on the allowlist buys an unauthenticated caller nothing.
"""

from __future__ import annotations

import pytest


def test_by_default_the_shell_origin_is_allowed_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With neither env var set, the allowlist is exactly the shell's origins.

    The desktop shell cannot be handed this at spawn time: it detect-or-spawns,
    so it routinely attaches to a daemon it did not start and could not have
    passed an environment variable to. And it carries no HTTP-proxy plugin, so
    the WebView makes these calls itself and really is cross-origin. Hence a
    default, not an opt-in.

    The Vite origin is NOT here — that one is a developer's opt-in.
    """
    monkeypatch.delenv("COFFER_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("COFFER_DEV_CORS", raising=False)
    from coffer.surfaces.http.cors import SHELL_ORIGINS, _resolve_origins

    assert _resolve_origins() == list(SHELL_ORIGINS)
    assert "http://localhost:5173" not in _resolve_origins()


def test_the_vite_dev_origin_is_allowed_only_behind_an_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`COFFER_DEV_CORS=1` is what admits the Vite dev server's origin.

    The dev UI runs on `localhost:5173` and talks to the daemon cross-origin,
    so it genuinely needs the entry — but only when a developer asks for it by
    setting the flag, never by default.
    """
    monkeypatch.delenv("COFFER_CORS_ORIGINS", raising=False)
    monkeypatch.setenv("COFFER_DEV_CORS", "1")
    from coffer.surfaces.http.cors import _resolve_origins

    origins = _resolve_origins()
    assert "http://localhost:5173" in origins
    # The opt-in adds to the shell's entry rather than replacing it, so a
    # developer running the app and Vite at once keeps both hosts working.
    assert "tauri://localhost" in origins


def test_an_explicit_list_replaces_everything_including_the_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`COFFER_CORS_ORIGINS` is the escape hatch, so it must really be total.

    A host this file does not know about needs a way to state its own origin,
    and a list that silently kept entries the operator did not write would not
    be one.
    """
    monkeypatch.delenv("COFFER_DEV_CORS", raising=False)
    monkeypatch.setenv("COFFER_CORS_ORIGINS", "https://example.test")
    from coffer.surfaces.http.cors import _resolve_origins

    assert _resolve_origins() == ["https://example.test"]
