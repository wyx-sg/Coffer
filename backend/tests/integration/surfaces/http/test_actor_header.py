"""The `X-Coffer-Actor` header — who the audit log says did it.

Every audited write records an actor, and the actor comes from a caller-supplied
header. Two things follow. It must have a safe default, or an audit entry ends
up attributed to `None`; and it must be validated, because the value is written
verbatim into a durable log that operators read and filter on, so an
unconstrained string is a log-injection surface (newlines, control characters,
32KB of padding) as well as an impersonation one.
"""

from __future__ import annotations


def test_a_missing_or_empty_actor_header_defaults_to_api() -> None:
    """Absent and empty both mean "no caller said" — recorded as `api`, never
    as `None` or an empty string, so every audit entry names someone."""
    from coffer.surfaces.http.dependencies import get_actor

    assert get_actor(None) == "api"
    assert get_actor("") == "api"


def test_the_actors_coffers_own_surfaces_send_are_all_accepted() -> None:
    """The CLI, the UI, the MCP shim and the e2e harnesses all pass an actor;
    each of those values must survive validation unchanged or their writes
    start failing."""
    from coffer.surfaces.http.dependencies import get_actor

    for v in ("cli", "api", "ui", "system", "e2e-mcp", "e2e-http", "test_runner"):
        assert get_actor(v) == v


def test_an_actor_that_could_corrupt_the_log_is_rejected_with_400() -> None:
    """Uppercase, whitespace, leading digits, shell-ish punctuation and
    over-length values are all refused. The rejection is a 400 — the caller
    sent something wrong, so the write must not happen at all rather than
    happen under a sanitised name."""
    import pytest
    from fastapi import HTTPException

    from coffer.surfaces.http.dependencies import get_actor

    for bad in ("UPPER", "has space", "x" * 33, "1starts-with-digit", "$pecial"):
        with pytest.raises(HTTPException) as exc_info:
            get_actor(bad)
        assert exc_info.value.status_code == 400
