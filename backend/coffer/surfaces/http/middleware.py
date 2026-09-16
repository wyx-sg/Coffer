"""The daemon's middleware stack, in one place, because the ORDER is the point.

Starlette runs the LAST-added middleware outermost, so this module reads
inside-out: the first call here ends up nearest the routes and the last call
ends up nearest the network. Each step's position is a correctness claim, not a
preference, which is why they live together rather than being sprinkled through
the composition root:

1. :mod:`coffer.surfaces.http.cors` — innermost. It only answers preflights and
   stamps headers on responses that got as far as a route.
2. :mod:`coffer.surfaces.http.host_guard` — wraps CORS. A request naming an
   authority this daemon does not answer for is a DNS-rebinding attempt and
   must be refused before CORS gets a chance to bless it.
3. :mod:`coffer.surfaces.http.trace` — outermost. A request gets its trace id
   before the host guard can refuse it, so even the refusal is correlatable:
   the 421 carries the same ``X-Coffer-Trace`` value as the log record that
   explains it.
"""

from __future__ import annotations

from fastapi import FastAPI

from coffer.surfaces.http import cors, host_guard, trace


def install(app: FastAPI) -> None:
    """Add every middleware, innermost first. See the module docstring."""
    cors.install(app)
    host_guard.install(app)
    trace.install(app)
