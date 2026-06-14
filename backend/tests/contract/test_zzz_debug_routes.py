"""TEMPORARY CI diagnostic — remove before merge."""

from __future__ import annotations


def test_debug_include_routers() -> None:
    import traceback

    import fastapi
    import starlette
    from fastapi import FastAPI

    from coffer.surfaces.http import routing

    app = FastAPI()
    before = len(app.routes)
    deltas = []
    err = None
    try:
        routing.include_all_routers(app)
    except Exception:
        err = traceback.format_exc()
    after_bulk = len(app.routes)

    # Per-router manual include to see which one(s) add 0 or raise.
    app2 = FastAPI()
    per = {}
    names = [
        "agent_router",
        "skill_router",
        "kb_router",
        "memory_router",
        "distill_router",
        "embedding_router",
        "projection_router",
    ]
    for n in names:
        r = getattr(routing, n, None)
        b = len(app2.routes)
        try:
            if r is not None:
                app2.include_router(r)
            per[n] = (len(getattr(r, "routes", [])), len(app2.routes) - b)
        except Exception as e:
            per[n] = f"RAISED {type(e).__name__}: {e}"

    diag = {
        "fastapi": fastapi.__version__,
        "starlette": starlette.__version__,
        "bulk_before": before,
        "bulk_after": after_bulk,
        "bulk_error": err,
        "per_router_(router_routes, added)": per,
    }
    raise AssertionError("INCLUDE_DIAGNOSTIC " + repr(diag))
