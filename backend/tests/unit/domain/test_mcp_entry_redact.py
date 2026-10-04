"""``redacted_config`` — one MCP entry whole, with every credential withheld."""

from __future__ import annotations

from coffer.domain.agent.mcp_entry_redact import MASK, redacted_config


def test_keeps_the_entry_shape_and_plain_fields():
    raw = {"command": "npx", "args": ["-y", "pkg"], "_skynet_version": "1.2.3", "timeout": 30}
    assert redacted_config(raw) == raw


def test_every_env_and_header_value_is_withheld_but_names_stay():
    raw = {
        "env": {"API_TOKEN": "s3cret", "LOG_LEVEL": "debug"},
        "headers": {"Authorization": "Bearer abc", "X-Plain": "v"},
        "http_headers": {"X-Api-Key": "k"},
        "environment": {"A": "b"},
    }
    out = redacted_config(raw)
    assert out["env"] == {"API_TOKEN": MASK, "LOG_LEVEL": MASK}
    assert out["headers"] == {"Authorization": MASK, "X-Plain": MASK}
    assert out["http_headers"] == {"X-Api-Key": MASK}
    assert out["environment"] == {"A": MASK}


def test_values_of_secret_looking_keys_are_withheld_at_any_depth():
    raw = {
        "token": "t",
        "api_key": "k",
        "key": "plain-key",
        "password": "p",
        "authorization": "a",
        "nested": {"client_secret": "x", "fine": "y"},
        "turn_limit": 3,
        "empty_token": "",
    }
    out = redacted_config(raw)
    assert out["token"] == out["api_key"] == out["key"] == MASK
    assert out["password"] == out["authorization"] == MASK
    assert out["nested"] == {"client_secret": MASK, "fine": "y"}
    assert out["turn_limit"] == 3
    assert out["empty_token"] == ""


def test_args_flag_values_urls_and_bearer_strings_are_withheld():
    raw = {
        "command": "npx",
        "args": [
            "mcp-remote",
            "https://user:hunter2@host.example/mcp?sig=abc&mode=fast&api_key=zzz",
            "--api-key=abc123",
            "--token",
            "tok-value",
            "--header",
            "Authorization: Bearer abc.def",
            "--verbose",
        ],
        "url": "https://h.example/sse?token=1",
    }
    out = redacted_config(raw)
    assert out["args"] == [
        "mcp-remote",
        f"https://user:{MASK}@host.example/mcp?sig=abc&mode=fast&api_key={MASK}",
        f"--api-key={MASK}",
        "--token",
        MASK,
        "--header",
        f"Authorization: Bearer {MASK}",
        "--verbose",
    ]
    assert out["url"] == f"https://h.example/sse?token={MASK}"
    flat = repr(out)
    for secret in ("hunter2", "abc123", "tok-value", "abc.def", "zzz"):
        assert secret not in flat


def test_a_command_array_is_treated_like_args():
    out = redacted_config({"command": ["tool", "--password=pw", "--ok=1"]})
    assert out["command"] == ["tool", f"--password={MASK}", "--ok=1"]
