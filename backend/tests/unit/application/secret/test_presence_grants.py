"""Presence grants (spec secret "Release plaintext only to a present human
in the desktop app"; design D1 test vector shared with the desktop shell)."""

from __future__ import annotations

import pytest

from coffer.application.secret.presence import PresenceGrants, derive_grant_key, sign_grant
from coffer.domain.secret_errors import PresenceGrantInvalid

_KEY = b"ZmFrZS1tYXN0ZXIta2V5LWZvci10ZXN0cy0wMDAwMDA="


def test_the_grant_key_and_signatures_match_the_shared_vector() -> None:
    gk = derive_grant_key(_KEY + b"\n")
    assert gk.hex() == "84cccae592fbe9961c40a663f512eaa2045d99f3ccd974e92fddbf8ea4492347"
    assert (
        sign_grant(gk, "reveal", "gh/token", "nonce-123")
        == "8654e8c12fcba0b8617f06e3c84c9636ab6d5a0a3b5221d531d1dc08c7a6cd50"
    )
    assert (
        sign_grant(gk, "approve", "0123456789abcdef", "nonce-456")
        == "13c3e5b98ae8c394f98b1f1631ac06e4d886b604876383fc29aee12b6118892c"
    )
    assert (
        sign_grant(gk, "export_master_key", "/Users/me/Backups", "nonce-789")
        == "2382008c76facbd67f01aacbf1da779c690ae654af87f9a8bf5ade889cfba3bd"
    )


def test_the_batch_target_matches_the_shared_vector_whatever_the_order() -> None:
    from coffer.domain.secrets import batch_target

    want = "batch:53e1eee92f2845fea31f392664f71343ccd188245a4ef042c22d86f32e08ee2d"
    assert batch_target([("b2", "fp2"), ("a1", "fp1")]) == want
    assert batch_target([("a1", "fp1"), ("b2", "fp2")]) == want
    assert batch_target([("a1", "fp1")]) != want
    assert batch_target([("a1", "fp1"), ("b2", "fpX")]) != want


def _grants(clock: list[float]) -> tuple[PresenceGrants, bytes]:
    gk = derive_grant_key(_KEY)
    return PresenceGrants(lambda: gk, clock=lambda: clock[0]), gk


def test_a_grant_is_redeemed_once() -> None:
    grants, gk = _grants([0.0])
    c = grants.challenge("reveal", "gh/token")
    grants.redeem("reveal", "gh/token", c.nonce, sign_grant(gk, "reveal", "gh/token", c.nonce))
    with pytest.raises(PresenceGrantInvalid):
        grants.redeem("reveal", "gh/token", c.nonce, sign_grant(gk, "reveal", "gh/token", c.nonce))


def test_a_bad_signature_burns_the_challenge() -> None:
    grants, gk = _grants([0.0])
    c = grants.challenge("reveal", "gh/token")
    with pytest.raises(PresenceGrantInvalid):
        grants.redeem("reveal", "gh/token", c.nonce, "0" * 64)
    with pytest.raises(PresenceGrantInvalid):
        grants.redeem("reveal", "gh/token", c.nonce, sign_grant(gk, "reveal", "gh/token", c.nonce))


def test_a_grant_for_one_target_or_operation_opens_no_other() -> None:
    grants, gk = _grants([0.0])
    c = grants.challenge("reveal", "gh/token")
    with pytest.raises(PresenceGrantInvalid):
        grants.redeem("reveal", "other", c.nonce, sign_grant(gk, "reveal", "other", c.nonce))
    c = grants.challenge("reveal", "gh/token")
    with pytest.raises(PresenceGrantInvalid):
        signed = sign_grant(gk, "approve", "gh/token", c.nonce)
        grants.redeem("approve", "gh/token", c.nonce, signed)


def test_a_challenge_expires() -> None:
    clock = [0.0]
    grants, gk = _grants(clock)
    c = grants.challenge("approve", "abc")
    clock[0] = 121.0
    with pytest.raises(PresenceGrantInvalid):
        grants.redeem("approve", "abc", c.nonce, sign_grant(gk, "approve", "abc", c.nonce))


def test_an_unknown_operation_gets_no_challenge() -> None:
    grants, _gk = _grants([0.0])
    with pytest.raises(PresenceGrantInvalid):
        grants.challenge("dump_everything", "x")
