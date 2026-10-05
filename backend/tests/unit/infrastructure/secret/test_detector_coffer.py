"""Coffer's allowlist and rules on top of the bundled gitleaks rules, the
detector's de-duplication, key extraction and multi-line values
(spec secret "Detect plaintext secrets with the bundled rules").

Every secret is built at runtime from seeded pieces so the repository's own
secret scan never sees a literal that looks like a key.
"""

from __future__ import annotations

import pathlib
import string

import pytest

from coffer.infrastructure.secret import detector, plaintext_findings
from tests.support.gitleaks_hand_samples import rand

HEX = "0123456789abcdef"
ID = rand("ref", 32, HEX)
HIGH = rand("high", 32)
PASSWORD = "Summer" + "2024!"
GH = "ghp_" + rand("gh", 36)
STRIPE = "sk_" + "live_" + rand("stripe", 24)
ANTHROPIC = (
    "sk-ant-" + "api03-" + rand("anthropic", 93, string.ascii_letters + string.digits) + "AA"
)
JWT = "ey" + rand("jwt", 20) + ".ey" + rand("jwt", 24) + "." + rand("jwt", 30)


def rules(text: str, path: str = "") -> list[str]:
    return [d.rule for d in detector.detect(text, path)]


def values(text: str, path: str = "") -> list[str]:
    return [text[d.start : d.end] for d in detector.detect(text, path)]


@pytest.mark.acceptance(
    spec="secret", scenario="a secret reference is not a finding though it looks like a key"
)
@pytest.mark.parametrize(
    "text",
    [
        f"API_KEY=coffer://secret/{ID}",
        f"API_KEY=coffer://secret/{ID}\n",
        "API_KEY=coffer://secret/github",
        'token: "coffer://secret/orders-db"',
        f'  "GITHUB_TOKEN": "secret/{ID}"',
        f'{{"secret_refs": {{"GITHUB_TOKEN": "secret/{ID}", "API_KEY": "secret/{ID}"}}}}',
    ],
)
def test_a_secret_reference_is_not_a_finding(text: str) -> None:
    assert detector.detect(text) == []


@pytest.mark.acceptance(
    spec="secret", scenario="a secret reference is not a finding though it looks like a key"
)
def test_a_server_citing_a_ref_reports_nothing_in_a_scan() -> None:
    config = {
        "transport": {
            "env": {"GITHUB_TOKEN": f"coffer://secret/{ID}", "API_KEY": f"secret/{ID}"},
            "headers": {"Authorization": "${API_TOKEN}"},
        },
    }
    assert plaintext_findings.scan_server("uid", "github", config) == []


@pytest.mark.parametrize(
    "line",
    [
        "API_KEY=$API_KEY_FROM_VAULT",
        "API_KEY=${API_KEY_FROM_VAULT}",
        "api_key: {{ .Values.apiKey }}",
        "token: ${{ secrets.GITHUB_TOKEN }}",
        "API_KEY=<your-api-key>",
        "API_KEY=xxxxxxxxxxxxxxxxxxxxxxxx",
        "password: changeme",
        "secret: example-secret-value",
        "token: REDACTED",
        "export DB_PASSWORD=${DB_PASSWORD_FROM_VAULT}",
        "coffer run --secret PGPASSWORD=orders-db -- psql",
        "coffer run --secret API_KEY=github -- ./deploy",
    ],
)
def test_references_interpolations_and_placeholders_are_not_findings(line: str) -> None:
    assert detector.detect(line) == []


CODE_LINES = [
    "    verb, token = m.group(1), m.group(0)",
    '    user, _, password = creds.partition(":")',
    "        password=password,",
    "    api_key = keys[0]",
]
CODE_READING = [
    "  const token = process.env.SPACE_TOKEN || require(resolveSdkPath()).resolveSpaceToken();",
    "  let token=process.env.SPACE_TOKEN?.trim();",
    "      if (fs.existsSync(f)) { token=req(f).resolveSpaceToken(); break; }",
    "    token=page.next_page_token;",
    '    token = args.token or os.environ.get("SPACE_TOKEN")',
    'api_key = os.environ["OPENAI_API_KEY"]',
    'password = os.getenv("DB_PASSWORD")',
    "const apiKey = import.meta.env.VITE_API_KEY",
    "token: env.GITHUB_TOKEN",
    "secret_key = settings.secret_key",
    "const token = config.authToken",
    "token = getToken()",
    "const token = accessToken",
    "    self.password = password_hash",
    "this.apiKey = resolvedKey",
]


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="code that assigns a secret-named variable is not a plaintext secret",
)
def test_code_assigning_a_secret_named_variable_is_not_reported() -> None:
    assert detector.detect("\n".join(CODE_LINES)) == []


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="code that reads a secret from elsewhere is not a plaintext secret",
)
@pytest.mark.parametrize("line", CODE_READING)
def test_code_reading_a_secret_from_elsewhere_is_not_reported(line: str) -> None:
    assert detector.detect(line) == []


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="code that reads a secret from elsewhere is not a plaintext secret",
)
@pytest.mark.parametrize(
    ("line", "key"),
    [
        (f'token = "{HIGH}"', "token"),
        (f"API_KEY={HIGH}", "API_KEY"),
        (f"export API_KEY={HIGH}", "API_KEY"),
        (f'  "api_key": "{HIGH}",', "api_key"),
    ],
)
def test_a_high_entropy_literal_assigned_to_a_secret_name_is_still_reported(
    line: str, key: str
) -> None:
    found = detector.detect(line)
    assert [(d.rule, d.key) for d in found] == [(detector.GENERIC_RULE, key)]
    assert line[found[0].start : found[0].end] == HIGH


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="code that reads a secret from elsewhere is not a plaintext secret",
)
def test_a_json_web_token_is_a_value() -> None:
    found = detector.detect(f"id_token: {JWT}")
    assert [d.rule for d in found] == ["jwt"]
    assert f"id_token: {JWT}"[found[0].start : found[0].end] == JWT


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="code that reads a secret from elsewhere is not a plaintext secret",
)
@pytest.mark.parametrize(
    "line",
    [
        f"const token = process.env.SPACE_TOKEN || '{GH}'",
        f"token = args.token or '{GH}'",
        f"const token = {GH}",
    ],
)
def test_a_token_beside_a_code_read_is_still_reported(line: str) -> None:
    assert values(line) == [GH]
    assert rules(line) == ["github-pat"]


def test_a_value_two_rules_find_is_one_finding_named_by_the_specific_rule() -> None:
    line = f'api_key = "{STRIPE}"'
    found = detector.detect(line)
    assert [d.rule for d in found] == ["stripe-access-token"]
    assert found[0].key == "api_key"
    assert line[found[0].start : found[0].end] == STRIPE


def test_a_finding_carries_where_the_value_is_never_the_value() -> None:
    found = detector.detect("x = 1\n" + f"API_KEY={HIGH}\n")
    assert len(found) == 1
    assert HIGH not in repr(found[0])
    assert [(n, d.rule) for n, d in detector.by_line("x = 1\n" + f"API_KEY={HIGH}\n", found)] == [
        (2, detector.GENERIC_RULE)
    ]


def test_the_key_is_the_name_assigned_on_the_line() -> None:
    assert detector.detect(f"export DB_API_KEY={HIGH}")[0].key == "DB_API_KEY"
    assert detector.detect(f"client_secret: '{HIGH}'")[0].key == "client_secret"
    assert detector.detect(f"see {GH} for it")[0].key == ""


def test_a_value_on_a_later_line_is_found_at_its_line() -> None:
    text = "\n".join(["# notes", "", f"token: {GH}", "end"])
    found = detector.detect(text)
    lines = detector.Lines(text)
    assert [lines.number(d.start) for d in found] == [3]
    assert lines.line(3) == f"token: {GH}"


@pytest.mark.acceptance(spec="secret", scenario="a vendor token is found and named by its rule")
def test_a_vendor_token_is_found_and_named_by_its_rule(tmp_path: pathlib.Path) -> None:
    script = tmp_path / "deploy" / "run.sh"
    script.parent.mkdir()
    script.write_text(f"#!/bin/sh\ncharge {STRIPE}\ncall {ANTHROPIC}\n", encoding="utf-8")
    hits, checked = plaintext_findings.scan_skills(tmp_path)
    assert checked == 1
    assert [(h.finding.line, h.finding.rule) for h in hits] == [
        (2, "stripe-access-token"),
        (3, "anthropic-api-key"),
    ]
    assert [h.value for h in hits] == [STRIPE, ANTHROPIC]
    # The finding that goes over the wire names a file, a line and a rule, never the value.
    assert all(STRIPE not in repr(h.finding) and ANTHROPIC not in repr(h.finding) for h in hits)


@pytest.mark.acceptance(spec="secret", scenario="a vendor token is found and named by its rule")
def test_a_vendor_token_on_a_plain_line_is_named_by_its_rule() -> None:
    text = f"charge {STRIPE}\ncall {ANTHROPIC}\n"
    assert rules(text) == ["stripe-access-token", "anthropic-api-key"]
    assert values(text) == [STRIPE, ANTHROPIC]


PEM_BODY = "\n".join(rand("pem", 64) for _ in range(4))
PEM = "-----BEGIN " + "RSA PRIVATE KEY-----\n" + PEM_BODY + "\n-----END " + "RSA PRIVATE KEY-----"


def test_a_private_key_is_one_finding_on_its_first_line_spanning_the_block() -> None:
    text = f"# deploy key\nkey: |\n{PEM}\ntrailing: 1\n"
    found = detector.detect(text)
    assert [d.rule for d in found] == ["private-key"]
    d = found[0]
    lines = detector.Lines(text)
    assert lines.number(d.start) == 3
    assert text[d.start : d.end].count("\n") >= 3
    assert "trailing" not in text[d.start : d.end]
    segments = list(lines.segments(d.start, d.end))
    assert segments[0][0] == 3 and len(segments) >= 4


def test_a_password_named_key_is_found_whatever_its_entropy() -> None:
    found = detector.detect(f"DB_PASSWORD={PASSWORD}")
    assert [(d.rule, d.key) for d in found] == [("coffer-password-assignment", "DB_PASSWORD")]
    assert values(f"DB_PASSWORD={PASSWORD}") == [PASSWORD]


@pytest.mark.parametrize(
    "line",
    [
        "DB_PASSWORD=short",
        "password: some_lowercase_identifier",
        "PASSWORD: SOME_UPPERCASE_IDENTIFIER",
        "password = os.getenv('DB_PASSWORD')",
        "password: ${DB_PASSWORD}",
    ],
)
def test_a_password_key_is_not_a_finding_for_a_short_value_an_identifier_or_code(
    line: str,
) -> None:
    assert detector.detect(line) == []


def test_a_password_inside_a_url_is_found() -> None:
    text = "DATABASE_URL=postgres://orders:" + PASSWORD + "@db.internal:5432/orders"
    found = detector.detect(text)
    assert [d.rule for d in found] == ["coffer-url-password"]
    assert text[found[0].start : found[0].end] == PASSWORD
    assert detector.detect("postgres://orders:${DB_PASSWORD}@db.internal/orders") == []
    assert detector.detect("https://user:password@host.example/x") == []


@pytest.mark.parametrize(
    ("key", "value", "rule"),
    [
        ("API_KEY", HIGH, "generic-api-key"),
        ("DB_PASSWORD", PASSWORD, "coffer-password-assignment"),
        ("API_TOKEN", "abab" * 4, "coffer-server-setting"),
        ("Authorization", "Bearer " + rand("bearer", 24), "coffer-server-setting"),
        ("X-Custom", "Token " + rand("token", 24), "coffer-server-setting"),
        ("API_KEY", ANTHROPIC, "anthropic-api-key"),
    ],
)
def test_an_mcp_server_setting_is_found_by_its_key_or_its_form(
    key: str, value: str, rule: str
) -> None:
    assert detector.detect_setting(key, value) == rule


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("LOG_LEVEL", "debug-verbose-mode"),
        ("API_KEY", "short"),
        ("API_KEY", "${API_TOKEN}"),
        ("API_KEY", "<your-token>"),
        ("API_KEY", f"coffer://secret/{ID}"),
        ("API_KEY", f"secret/{ID}"),
    ],
)
def test_an_mcp_server_setting_that_is_not_a_secret_is_not_found(key: str, value: str) -> None:
    assert detector.detect_setting(key, value) is None
