"""build_attention_sources: one source per kind, and a missing dependency
leaves its source out."""

from __future__ import annotations

from typing import Any

from coffer.surfaces.http.attention_wiring import build_attention_sources

_STUB: Any = object()


def test_every_source_when_every_dependency_is_wired() -> None:
    sources = build_attention_sources(
        resource_svc=_STUB,
        credential_store=_STUB,
        connection_service=_STUB,
        auto_detect=_STUB,
        sync_service=_STUB,
        channel_service=_STUB,
        health_repo=_STUB,
    )
    assert [(s.name, s.feature) for s in sources] == [
        ("mcp_server", None),
        ("agent", None),
        ("channel", None),
        ("sync", "vault_sync"),
    ]


def test_an_unwired_dependency_skips_its_source() -> None:
    sources = build_attention_sources(
        resource_svc=_STUB,
        credential_store=_STUB,
        connection_service=_STUB,
        auto_detect=_STUB,
        sync_service=None,
        channel_service=None,
        health_repo=None,
    )
    assert [s.name for s in sources] == ["agent"]
