"""PairingManager: issue/pending/claim lifecycle with an injected clock."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from coffer.application.channel.pairing import PairingManager, start_link

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
START = datetime(2026, 6, 12, 9, 0, 0, tzinfo=UTC)


class Clock:
    def __init__(self, now: datetime = START) -> None:
        self.now = now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def manager(clock: Clock) -> PairingManager:
    return PairingManager(ttl_seconds=3600, max_attempts=3, now_fn=clock)


def test_issue_returns_8_char_code_from_unambiguous_alphabet(manager: PairingManager):
    code, _ = manager.issue("ch")
    assert len(code) == 8
    assert set(code) <= set(ALPHABET)
    assert not set(code) & set("0O1I")


def test_issue_expires_at_is_now_plus_ttl(clock: Clock, manager: PairingManager):
    _, expires_at = manager.issue("ch")
    assert expires_at == clock.now + timedelta(seconds=3600)


def test_pending_false_before_issue_true_after(manager: PairingManager):
    assert manager.pending("ch") is False
    manager.issue("ch")
    assert manager.pending("ch") is True


def test_pending_false_after_expiry(clock: Clock, manager: PairingManager):
    manager.issue("ch")
    clock.advance(3600)
    assert manager.pending("ch") is False


def test_claim_consumes_code(manager: PairingManager):
    code, _ = manager.issue("ch")
    assert manager.try_claim("ch", code) is True
    assert manager.pending("ch") is False
    assert manager.try_claim("ch", code) is False


def test_claim_is_case_insensitive_and_strips_whitespace(manager: PairingManager):
    code, _ = manager.issue("ch")
    assert manager.try_claim("ch", f"  {code.lower()} \n") is True


def test_claim_without_pending_code_fails(manager: PairingManager):
    assert manager.try_claim("ch", "ABCDEFGH") is False


def test_claim_scoped_per_channel(manager: PairingManager):
    code, _ = manager.issue("ch-a")
    assert manager.try_claim("ch-b", code) is False
    assert manager.try_claim("ch-a", code) is True


def test_wrong_guess_burns_attempt_but_code_survives(manager: PairingManager):
    code, _ = manager.issue("ch")
    assert manager.try_claim("ch", "WRONGGGG") is False
    assert manager.pending("ch") is True
    assert manager.try_claim("ch", code) is True


@pytest.mark.acceptance(spec="channels", scenario="an expired or wrong code does not pair")
def test_expired_or_wrong_code_does_not_pair(clock: Clock):
    manager = PairingManager(ttl_seconds=3600, max_attempts=3, now_fn=clock)

    # Wrong guesses burn attempts; exhaustion invalidates the code entirely.
    code, _ = manager.issue("ch")
    for _ in range(3):
        assert manager.try_claim("ch", "WRONGGGG") is False
    assert manager.pending("ch") is False
    assert manager.try_claim("ch", code) is False  # even the right code is dead

    # An expired code fails to claim.
    code, expires_at = manager.issue("ch")
    clock.now = expires_at
    assert manager.try_claim("ch", code) is False
    assert manager.pending("ch") is False


def test_clear_drops_pending_code(manager: PairingManager):
    code, _ = manager.issue("ch")
    manager.clear("ch")
    assert manager.pending("ch") is False
    assert manager.try_claim("ch", code) is False


def test_clear_without_pending_code_is_noop(manager: PairingManager):
    manager.clear("ch")  # must not raise
    assert manager.pending("ch") is False


def test_reissue_replaces_old_code(manager: PairingManager):
    old_code, _ = manager.issue("ch")
    new_code, _ = manager.issue("ch")
    if new_code == old_code:  # 32**-8 collision; re-roll to keep the test meaningful
        new_code, _ = manager.issue("ch")
    assert manager.try_claim("ch", old_code) is False
    assert manager.pending("ch") is True  # wrong guess burned an attempt, code survives
    assert manager.try_claim("ch", new_code) is True


def test_reissue_resets_attempt_budget(manager: PairingManager):
    manager.issue("ch")
    assert manager.try_claim("ch", "WRONGGGG") is False
    assert manager.try_claim("ch", "WRONGGGG") is False
    code, _ = manager.issue("ch")  # fresh budget of 3
    assert manager.try_claim("ch", "WRONGGGG") is False
    assert manager.try_claim("ch", "WRONGGGG") is False
    assert manager.pending("ch") is True
    assert manager.try_claim("ch", code) is True


# -- deep-link pairing (FR-066) ----------------------------------------------


def test_start_link_carries_the_code() -> None:
    assert start_link("cofferbot", "ABC12345") == "https://t.me/cofferbot?start=ABC12345"


def test_start_link_is_empty_without_a_username() -> None:
    # Nothing to build a link from — the typed code stays the only way in.
    assert start_link("", "ABC12345") == ""


def test_a_start_payload_claims_the_code() -> None:
    manager = PairingManager()
    code, _ = manager.issue("tg")
    assert manager.try_claim("tg", f"/start {code}") is True
    # Single use holds for the link form exactly as for the typed one.
    assert manager.try_claim("tg", f"/start {code}") is False


def test_a_start_payload_addressed_to_the_bot_claims_the_code() -> None:
    manager = PairingManager()
    code, _ = manager.issue("tg")
    assert manager.try_claim("tg", f"/start@cofferbot {code}") is True


def test_a_lowercase_start_payload_claims_the_code() -> None:
    manager = PairingManager()
    code, _ = manager.issue("tg")
    assert manager.try_claim("tg", f"/start {code.lower()}") is True


def test_a_wrong_start_payload_burns_an_attempt() -> None:
    manager = PairingManager(max_attempts=1)
    code, _ = manager.issue("tg")
    assert manager.try_claim("tg", "/start WRONGONE") is False
    # The budget is shared: one wrong link exhausts it and kills the code.
    assert manager.try_claim("tg", code) is False


def test_a_bare_start_is_not_a_claim() -> None:
    manager = PairingManager()
    manager.issue("tg")
    assert manager.try_claim("tg", "/start") is False
