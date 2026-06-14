"""TEMPORARY CI diagnostic — remove before merge.

The test-contract job reports kb/memory/distill routes missing from the app on
Linux while macOS local passes. This dumps per-router route counts and import
state so we can see WHICH router objects are empty and why.
"""

from __future__ import annotations


def test_debug_router_route_counts() -> None:
    import sys

    from coffer.surfaces.http import routing
    from coffer.surfaces.http.app import create_app

    names = [
        "kb_router",
        "memory_router",
        "distill_router",
        "embedding_router",
        "projection_router",
        "agent_router",
        "skill_router",
    ]
    counts = {}
    for n in names:
        r = getattr(routing, n, None)
        counts[n] = None if r is None else len(getattr(r, "routes", []))

    from coffer.main import app as main_app

    main_paths = sorted({getattr(rt, "path", "") for rt in main_app.routes})
    app = create_app()
    app_paths = sorted({getattr(rt, "path", "") for rt in app.routes})

    # Which spec-006/007 modules are in sys.modules and do their routers have routes?
    suspect_mods = [
        m for m in sys.modules if "knowledge_base" in m or "http.memory" in m or "http.distill" in m
    ]

    diag = {
        "router_route_counts": counts,
        "app_path_count": len(app_paths),
        "has_kb_path": any(p.startswith("/api/v1/knowledge_bases") for p in app_paths),
        "has_memory_path": any(p.startswith("/api/v1/memory_stores") for p in app_paths),
        "has_transcripts_path": any("transcripts" in p for p in app_paths),
        "main_app_has_kb": any(p.startswith("/api/v1/knowledge_bases") for p in main_paths),
        "fresh_eq_main": app_paths == main_paths,
        "suspect_modules": sorted(suspect_mods),
        "all_paths": app_paths,
    }
    # Force the diagnostic into the failure output.
    raise AssertionError("ROUTE_DIAGNOSTIC " + repr(diag))
