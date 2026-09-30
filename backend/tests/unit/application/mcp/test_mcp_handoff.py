"""The MCP server hand-off prompts: what they say, and what they never say."""

from __future__ import annotations

import pytest

from coffer.application.mcp.handoff import diagnose_handoff, launcher_handoff
from coffer.domain.handoff import STANDING_RULES
from coffer.domain.mcp.config_summary import redacted_url, scrub

ARG_TOKEN = "tok_4f9a8b7c6d5e"
ENV_VALUE = "hunter2-value"
HEADER_VALUE = "hdr-value-9876"
BEARER = "abcdefghijklmnopqrstuvwxyz0123"
GH_TOKEN = "ghp_" + "a1b2c3d4e5" * 3

STDIO = {
    "transport": {
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "@acme/mcp", "--api-key", ARG_TOKEN, f"--github={GH_TOKEN}"],
        "env": {"ACME_REGION": ENV_VALUE},
        "secret_refs": {"ACME_TOKEN": "coffer://secret/acme"},
        "cwd": "/work/acme",
    }
}


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="the diagnosis prompt never carries a secret value"
)
def test_the_diagnosis_prompt_names_keys_and_never_a_value() -> None:
    prompt = diagnose_handoff(
        name="acme",
        config=STDIO,
        error=f"exited: api_key={ARG_TOKEN} rejected",
        stderr=["starting", f"Authorization: Bearer {BEARER}", f"token={GH_TOKEN}"],
        machine="macOS 15.6, arm64",
        log_path="/logs/upstream/acme.log",
    )
    for value in (ARG_TOKEN, ENV_VALUE, BEARER, GH_TOKEN, "coffer://secret/acme"):
        assert value not in prompt
    assert "ACME_REGION" in prompt and "ACME_TOKEN" in prompt
    assert "`npx -y @acme/mcp --api-key '<secret>' '--github=<secret>'`" in prompt
    assert "Working directory: /work/acme." in prompt
    assert "    starting" in prompt
    assert "/logs/upstream/acme.log" in prompt
    assert "coffer mcp test acme" in prompt
    assert "Do not read or change the secrets Coffer stores" in prompt
    assert all(rule in prompt for rule in STANDING_RULES)


def test_an_http_server_is_summarised_by_its_redacted_url_and_header_names() -> None:
    prompt = diagnose_handoff(
        name="web",
        config={
            "transport": {
                "type": "http",
                "url": "https://user:pw@mcp.example.com/mcp?api_key=zzz999&region=eu",
                "headers": {"X-Api-Key": HEADER_VALUE},
                "secret_refs": {"Authorization": "secret/web"},
            }
        },
        error=None,
        stderr=[],
        machine="Ubuntu 24.04 LTS, x86_64",
    )
    assert "https://<secret>@mcp.example.com/mcp?api_key=<secret>&region=eu" in prompt
    assert "Headers it sends (values not shown): X-Api-Key." in prompt
    assert HEADER_VALUE not in prompt and "zzz999" not in prompt and ":pw@" not in prompt
    assert "Its last connection test failed." in prompt


def test_only_the_newest_twenty_stderr_lines_are_quoted() -> None:
    lines = [f"line {i:02d}" for i in range(30)]
    prompt = diagnose_handoff(name="s", config=STDIO, error="boom", stderr=lines, machine="m")
    assert "line 29" in prompt and "line 10" in prompt and "line 09" not in prompt


def test_the_launcher_prompt_names_launcher_server_command_and_path_but_no_installer() -> None:
    prompt = launcher_handoff(
        name="acme", config=STDIO, runner="npx", machine="macOS 15.6, arm64", path="/usr/bin:/bin"
    )
    assert prompt.startswith("Please install `npx` on this machine")
    assert "MCP server acme" in prompt
    assert "`npx -y @acme/mcp --api-key '<secret>' '--github=<secret>'`" in prompt
    assert "/usr/bin:/bin" in prompt and "macOS 15.6, arm64" in prompt
    assert "started from the GUI" in prompt
    assert "coffer mcp test acme" in prompt
    for word in ("brew", "apt", "winget"):
        assert word not in prompt
    for value in (ARG_TOKEN, ENV_VALUE, GH_TOKEN):
        assert value not in prompt


def test_scrub_leaves_ordinary_text_alone() -> None:
    assert scrub("listening on port 8080") == "listening on port 8080"
    assert redacted_url("https://mcp.example.com/mcp") == "https://mcp.example.com/mcp"
