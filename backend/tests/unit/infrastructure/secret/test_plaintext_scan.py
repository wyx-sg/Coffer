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


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="code that reads a secret from elsewhere is not a plaintext secret",
)
@pytest.mark.parametrize(
    "line",
    [
        # The real skill-script lines that were reported.
        "  const token = process.env.SPACE_TOKEN || require(resolveSdkPath()).resolveSpaceToken();",
        "  let token=process.env.SPACE_TOKEN?.trim();",
        "      if (fs.existsSync(f)) { token=req(f).resolveSpaceToken(); break; }",
        "    token=page.next_page_token;",
        '    token = args.token or os.environ.get("SPACE_TOKEN")',
        # Environment reads and interpolations.
        'api_key = os.environ["OPENAI_API_KEY"]',
        'password = os.getenv("DB_PASSWORD")',
        "const apiKey = import.meta.env.VITE_API_KEY",
        "token: env.GITHUB_TOKEN",
        "token: ${{ secrets.GITHUB_TOKEN }}",
        "DB_PASSWORD=${DB_PASSWORD_FROM_VAULT}",
        "DB_PASSWORD=$DB_PASSWORD_FROM_VAULT",
        # Members, calls and bare names in code.
        "secret_key = settings.secret_key",
        "const token = config.authToken",
        "token = getToken()",
        "const token = accessToken",
        "    self.password = password_hash",
        "this.apiKey = resolvedKey",
        # Placeholders.
        "API_KEY=<your-api-key>",
        "password: changeme",
        "token: dummy-token-value",
        "secret: REDACTED",
    ],
)
def test_code_reading_a_secret_from_elsewhere_is_not_reported(line: str) -> None:
    assert find_in_text(line) == []


AWS = "AKIA" + "ABCDEFGH" + "23456789"
SLACK = "xoxb-" + "1234567890-abcdefghij"
OPENAI = "sk-" + "Ab3x" * 6
MIXED = "a1b2" + "c3d4.e5f6" + "g7h8"
JWT = "eyJ" + "hbGciOi" + ".eyJ" + "zdWIiOi" + ".c2lnbmF0dXJl"


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="code that reads a secret from elsewhere is not a plaintext secret",
)
@pytest.mark.parametrize(
    "line",
    [
        f"const token = process.env.SPACE_TOKEN || '{TOKEN}'",
        f"token = config.{TOKEN}",
        f"const token = {TOKEN}",
        f"aws = {AWS}",
        f"slack.post(token={SLACK})",
        f"client = OpenAI(api_key=os.environ.get('K') or '{OPENAI}')",
    ],
)
def test_a_known_token_shape_next_to_code_is_still_reported(line: str) -> None:
    assert "token" in [key for _, key in find_in_text(line)]


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="code that reads a secret from elsewhere is not a plaintext secret",
)
@pytest.mark.parametrize(
    ("line", "key"),
    [
        (f"API_KEY={FAKE}", "API_KEY"),
        (f"export DB_PASSWORD={FAKE}", "DB_PASSWORD"),
        (f"token: {FAKE}", "token"),
        (f'const token = "{FAKE}"', "token"),
        (f"password = 'process.env.{FAKE}'", "password"),
        # A JSON Web Token is dotted, and is a value.
        (f"id_token: {JWT}", "id_token"),
        # A dotted value whose parts mix in digits is not a name.
        (f"secret: {MIXED}", "secret"),
    ],
)
def test_literals_are_still_reported(line: str, key: str) -> None:
    assert find_in_text(line) == [(1, key)]
