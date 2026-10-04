"""What the plaintext scan treats as a secret: assigned literals and token shapes, not code."""

from __future__ import annotations

import pytest

from coffer.infrastructure.secret.plaintext_scan import find_in_text, mask_line


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="code that assigns a secret-named variable is not a plaintext secret",
)
def test_code_assigning_a_secret_named_variable_is_not_reported() -> None:
    code = "\n".join(
        [
            "    verb, token = m.group(1), m.group(0)",
            '    user, _, password = creds.partition(":")',
            "        password=password,",
            "    api_key = keys[0]",
        ]
    )
    assert find_in_text(code) == []


# Built at runtime so the repository's own secret scanner never sees a
# literal that looks like a key.
FAKE = "fixture" + "-value-" + "0000"


def test_assigned_literals_are_still_reported() -> None:
    text = "\n".join([f'password = "{FAKE}"', f"API_KEY={FAKE}"])
    assert find_in_text(text) == [(1, "password"), (2, "API_KEY")]


def test_a_quoted_literal_with_punctuation_is_still_reported() -> None:
    value = "a(b)c,d;" + "e[f]g"
    assert find_in_text(f'secret: "{value}"') == [(1, "secret")]


TOKEN = "ghp_" + "Ab3" * 12


def test_a_line_keeps_its_length_and_masks_every_value() -> None:
    raw = f'API_KEY="{FAKE}"  # and {TOKEN}'
    text, values = mask_line(raw)
    assert len(text) == len(raw)
    assert FAKE not in text and TOKEN[4:] not in text
    assert [v.key for v in values] == ["API_KEY", "token"]
    assert text[values[0].start : values[0].end] == "•" * len(FAKE)
    assert text.startswith('API_KEY="') and "# and ghp_" in text
