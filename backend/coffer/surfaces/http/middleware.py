"""The daemon's middleware stack, in one place, because the ORDER is the point.

Starlette runs the LAST-added middleware outermost, so this module reads
inside-out: the first call here ends up nearest the routes and the last call
ends up nearest the network. Each step's position is a correctness claim, not a
preference, which is why they live together rather than being sprinkled through
the composition root:

0. :mod:`coffer.surfaces.http.attention_freshness` — innermost, around the
   routes only: a request that may write drops the kept attention report. Its
   place does not matter for correctness as long as it sees every routed write.
1. :mod:`coffer.surfaces.http.setup_state` — next. While the daemon waits
   for git it refuses every route that needs the vault; it sits inside CORS so
   the page served from another origin can still read the refusal.
2. :mod:`coffer.surfaces.http.cors`. It only answers preflights
   and stamps headers on responses that got as far as a route.
3. :mod:`coffer.surfaces.http.host_guard` — wraps CORS. A request naming an
   authority this daemon does not answer for is a DNS-rebinding attempt, and
   one carrying a foreign ``Origin`` is another site's page; both must be
   refused before CORS gets a chance to bless them.
4. :mod:`coffer.surfaces.http.trace` — outermost. A request gets its trace id
   before the host guard can refuse it, so even the refusal is correlatable:
   the 403 carries the same ``X-Coffer-Trace`` value as the log record that
   explains it.
"""

from __future__ import annotations

from fastapi import FastAPI

from coffer.surfaces.http import cors, host_guard, setup_state, trace
from coffer.surfaces.http.attention_freshness import AttentionFreshness


def install(app: FastAPI) -> None:
    """Add every middleware, innermost first. See the module docstring."""
    app.add_middleware(AttentionFreshness)
    setup_state.install(app)
    cors.install(app)
    host_guard.install(app)
    trace.install(app)
