"""The capability key travels in the request BODY, not the path.

A capability key is an upstream-chosen identifier, and for resources it is a
URI — `file:///path/to/x`. A key like that cannot be a path segment: the
slashes make the router match a different (or no) route, and percent-encoding
is unreliable across proxies and clients. So enable/disable take the key in a
JSON body, and this pins the two properties that makes safe:
a slash-bearing key is accepted verbatim, and an empty key is refused rather
than quietly toggling nothing.

The route behaviour itself (404 on an unknown key, the audit entry, the
preference flip) lives in `test_capability_routes.py`; this is the wire model's
own contract, which is what stops a future route from re-introducing a
path-segment key.
"""

from __future__ import annotations


def test_a_capability_key_may_contain_slashes_but_may_not_be_empty() -> None:
    import pytest
    from pydantic import ValidationError

    from coffer.surfaces.http.schemas import CapabilityKeyBody

    # A resource URI — the reason the key is not a path segment.
    assert (
        CapabilityKeyBody(capability_key="file:///path/with/slashes").capability_key
        == "file:///path/with/slashes"
    )
    with pytest.raises(ValidationError):
        CapabilityKeyBody(capability_key="")
