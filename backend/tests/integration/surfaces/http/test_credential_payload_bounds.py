"""Bounds on the credential write payload.

A credential value is written straight into the OS keyring, which has its own
per-item size limits and no useful error when they are exceeded. Bounding the
value at the wire model means an oversized write is refused with a 422 naming
the field, instead of surfacing as an opaque keyring failure — and means an
unbounded body cannot be used to push arbitrary bulk into the keychain.
"""

from __future__ import annotations

import pytest


def test_a_credential_value_is_bounded_at_8192_bytes() -> None:
    """8192 is accepted and 8193 is refused — the bound is enforced at the
    wire model, so no route can accept a value the keyring cannot hold."""
    from pydantic import ValidationError

    from coffer.surfaces.http.schemas import CredentialSetIn

    CredentialSetIn(ref="ok", value="x" * 8192)  # boundary
    with pytest.raises(ValidationError):
        CredentialSetIn(ref="ok", value="x" * 8193)
