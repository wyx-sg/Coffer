"""What a masked plaintext value shows of itself (spec vault-sync "Show a
plaintext finding in its file"): its length, kinds of character, a token
format's public prefix and a hint — no other character of it."""

from __future__ import annotations

from coffer.domain.plaintext_shape import mask, shape_of

# Built at runtime so the repository's own secret scanner never sees a
# literal that looks like a key.
RANDOM = "Qz8" * 6
TOKEN = "ghp_" + "Ab3" * 12


def test_a_random_value_shows_only_its_length_and_kinds() -> None:
    shape = shape_of(RANDOM)
    assert (shape.length, shape.classes, shape.prefix, shape.hint) == (
        18,
        ("lower", "upper", "digit"),
        None,
        None,
    )
    assert mask(RANDOM, shape) == "•" * 18


def test_a_token_format_keeps_its_public_prefix() -> None:
    shape = shape_of(TOKEN)
    assert shape.prefix == "ghp_"
    assert mask(TOKEN, shape) == "ghp_" + "•" * (len(TOKEN) - 4)


def test_hints_for_code_placeholders_and_repeats() -> None:
    assert shape_of("process.env.API_TOKEN").hint == "reference"
    example = shape_of("my-example-key-123")
    assert (example.hint, example.word) == ("placeholder", "example")
    assert shape_of("aaaaaaaaaa").hint == "repeated"
