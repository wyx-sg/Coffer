"""SeaTalk callback signature: sha256(body + secret) hexdigest + verification."""

from __future__ import annotations

from coffer.domain.channel.signing import seatalk_signature, verify_seatalk_signature

BODY = b'{"event":"ping"}'
SECRET = "topsecret"
# Precomputed sha256(b'{"event":"ping"}' + b'topsecret').hexdigest()
KNOWN_SIGNATURE = "773109387ce4c5ff79f75b339422e1862be984e6926beedeb64058a9cb309fe5"


def test_signature_matches_known_vector():
    assert seatalk_signature(BODY, SECRET) == KNOWN_SIGNATURE


def test_signature_is_lowercase_hex_sha256():
    sig = seatalk_signature(b"abc", "s")
    assert len(sig) == 64
    assert sig == sig.lower()
    assert all(c in "0123456789abcdef" for c in sig)


def test_verify_accepts_exact_signature():
    assert verify_seatalk_signature(BODY, SECRET, KNOWN_SIGNATURE) is True


def test_verify_accepts_uppercase_signature():
    assert verify_seatalk_signature(BODY, SECRET, KNOWN_SIGNATURE.upper()) is True


def test_verify_accepts_whitespace_padded_signature():
    assert verify_seatalk_signature(BODY, SECRET, f"  {KNOWN_SIGNATURE}\n") is True


def test_verify_rejects_tampered_body():
    assert verify_seatalk_signature(b'{"event":"pong"}', SECRET, KNOWN_SIGNATURE) is False


def test_verify_rejects_wrong_secret():
    assert verify_seatalk_signature(BODY, "othersecret", KNOWN_SIGNATURE) is False


def test_verify_rejects_tampered_signature():
    tampered = ("f" if KNOWN_SIGNATURE[0] != "f" else "0") + KNOWN_SIGNATURE[1:]
    assert verify_seatalk_signature(BODY, SECRET, tampered) is False


def test_verify_rejects_empty_signature():
    assert verify_seatalk_signature(BODY, SECRET, "") is False
