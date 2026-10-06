"""The streaming exact-value masker that guards an upstream's stderr file.

Spec secret "Hold plaintext only in memory at the moment of use": a value
Coffer injected into a stdio child never reaches that child's log file, however
the child's writes happen to be chunked.
"""

from __future__ import annotations

import pytest

from coffer.infrastructure.mcp.stderr_mask import MASK, StreamMasker

#: Built at run time so a secret scanner never sees a key-shaped literal here.
SECRET = "-".join(["canary", "injected", "value", "0123456789"])


def _stream(masker: StreamMasker, chunks: list[bytes]) -> bytes:
    return b"".join(masker.feed(c) for c in chunks) + masker.finish()


def _every_split(data: bytes) -> list[list[bytes]]:
    return [[data[:i], data[i:]] for i in range(len(data) + 1)]


def test_an_empty_overlay_passes_everything_through_untouched() -> None:
    masker = StreamMasker([])
    assert not masker.active
    data = "plain ü line\n".encode()
    assert _stream(masker, [data[:3], data[3:]]) == data


def test_a_value_in_one_chunk_is_masked_and_its_neighbours_kept() -> None:
    out = _stream(StreamMasker([SECRET]), [f"key={SECRET} end\n".encode()])
    assert out == f"key={MASK} end\n".encode()


@pytest.mark.parametrize("split", range(len(f"a={SECRET}!") + 1))
def test_a_value_split_at_any_byte_is_still_masked(split: int) -> None:
    data = f"a={SECRET}!".encode()
    out = _stream(StreamMasker([SECRET]), [data[:split], data[split:]])
    assert out == f"a={MASK}!".encode()


def test_a_value_fed_one_byte_at_a_time_is_masked() -> None:
    data = f"x{SECRET}y{SECRET}".encode()
    out = _stream(StreamMasker([SECRET]), [bytes([b]) for b in data])
    assert out == f"x{MASK}y{MASK}".encode()


def test_a_value_ending_exactly_at_a_chunk_edge_is_masked() -> None:
    masker = StreamMasker([SECRET])
    first = masker.feed(f"head {SECRET}".encode())
    rest = masker.feed(b" tail\n") + masker.finish()
    assert SECRET.encode() not in first + rest
    assert first + rest == f"head {MASK} tail\n".encode()


def test_overlapping_occurrences_leave_no_whole_value() -> None:
    value = "abcabcab"
    data = ("abcabc" * 4).encode()
    for chunks in _every_split(data):
        out = _stream(StreamMasker([value]), chunks)
        assert value.encode() not in out


def test_several_values_of_different_lengths_are_all_masked() -> None:
    short, long_ = "tok1234", "tok1234-and-more-entropy"
    data = f"<{long_}|{short}|{long_[:10]}>".encode()
    for chunks in _every_split(data):
        out = _stream(StreamMasker([short, long_]), chunks)
        # The longer value is masked whole, not as its shorter prefix + a tail.
        assert out == f"<{MASK}|{MASK}|{MASK}-an>".encode(), chunks


def test_a_multibyte_value_is_masked_at_any_byte_split() -> None:
    value = "密钥-ключ-🔑-1"
    data = f"[{value}]".encode()
    for chunks in _every_split(data):
        assert _stream(StreamMasker([value]), chunks) == f"[{MASK}]".encode()


def test_values_shorter_than_the_minimum_are_not_masked() -> None:
    masker = StreamMasker(["abc", ""])
    assert not masker.active
    assert _stream(masker, [b"abc abc"]) == b"abc abc"


def test_text_that_only_resembles_a_value_is_not_rewritten() -> None:
    data = f"{SECRET[:-1]} {SECRET[1:]} {SECRET.upper()}\n".encode()
    for chunks in _every_split(data):
        assert _stream(StreamMasker([SECRET]), chunks) == data


def test_mask_text_masks_a_whole_coffer_line() -> None:
    masker = StreamMasker([SECRET])
    assert masker.mask_text(f"error PATH /x/{SECRET}:/bin") == f"error PATH /x/{MASK}:/bin"


def test_nothing_is_held_back_beyond_what_could_still_become_a_value() -> None:
    masker = StreamMasker([SECRET])
    out = masker.feed(b"0123456789" * 5)
    # Only the last len(SECRET) - 1 bytes may wait for the next chunk.
    assert len(out) == 50 - (len(SECRET) - 1)
    assert out + masker.finish() == b"0123456789" * 5
