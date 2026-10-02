"""Local model runtimes a connection may point at, and what each must be to
serve an agent natively (spec provider-switching "Configure a local model
connection").

A local connection is a keyless endpoint on this machine — Ollama, LM Studio,
vLLM, llama.cpp's ``llama-server`` — reached through the model proxy like any
other connection, with **no protocol translation**: every mainstream runtime
now speaks Anthropic Messages (for Claude Code) and OpenAI Responses (for
Codex) itself, so a Coffer translator would be a second translator, and would
break the proxy's byte-relay rules. A runtime that speaks neither wire —
``mlx_lm.server`` serves only Chat Completions — is not a supported upstream;
LM Studio's MLX engine serves the native wires instead.

Which wires a runtime serves depends on its version. The table below is the
minimum version per wire; a runtime Coffer detects below it is offered for
neither wire it lacks. ``llama-server`` builds carry date tags rather than a
comparable version, so it is taken at its word: Messages supported, Responses
marked experimental (its own README calls it partial).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Runtime(StrEnum):
    OLLAMA = "ollama"
    LMSTUDIO = "lmstudio"
    VLLM = "vllm"
    LLAMA_SERVER = "llama_server"


#: The wire names a local runtime is recorded as serving: the agents' own.
ANTHROPIC_WIRE = "anthropic"
OPENAI_WIRE = "openai"

#: ``runtime -> wire -> minimum version`` (inclusive). ``None``: no comparable
#: version exists; the wire is assumed.
MIN_VERSIONS: dict[Runtime, dict[str, tuple[int, ...] | None]] = {
    Runtime.OLLAMA: {ANTHROPIC_WIRE: (0, 14, 0), OPENAI_WIRE: (0, 13, 4)},
    Runtime.LMSTUDIO: {ANTHROPIC_WIRE: (0, 4, 1), OPENAI_WIRE: (0, 3, 29)},
    Runtime.VLLM: {ANTHROPIC_WIRE: (0, 11, 1), OPENAI_WIRE: (0, 10, 0)},
    Runtime.LLAMA_SERVER: {ANTHROPIC_WIRE: None, OPENAI_WIRE: None},
}

#: Below this many tokens the agents' own compaction and tool schemas do not
#: fit well; the Model tab warns (the runtimes' own guidance says 64k).
SMALL_WINDOW = 64_000

#: Default ports probed when no base URL is given. vLLM's default 8000 is
#: the Coffer daemon's own port, so vLLM is only found on a URL the user gives.
DEFAULT_PORTS: dict[Runtime, int] = {
    Runtime.OLLAMA: 11434,
    Runtime.LMSTUDIO: 1234,
    Runtime.LLAMA_SERVER: 8080,
}


def parse_version(text: str | None) -> tuple[int, ...] | None:
    """``"0.14.2"`` / ``"v0.30.0rc1"`` → ``(0, 14, 2)`` / ``(0, 30, 0)``."""
    if not text:
        return None
    parts: list[int] = []
    for chunk in text.strip().lstrip("vV").split("."):
        digits = ""
        for ch in chunk:
            if not ch.isdigit():
                break
            digits += ch
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) if parts else None


def served_wires(runtime: Runtime, version: str | None) -> list[str]:
    """The wires ``runtime`` at ``version`` serves natively. An unreadable
    version on a runtime that has minimums serves nothing: Coffer does not
    claim support it cannot check."""
    have = parse_version(version)
    out: list[str] = []
    for wire, minimum in MIN_VERSIONS[runtime].items():
        if minimum is None or (have is not None and have >= minimum):
            out.append(wire)
    return out


class LocalRuntime(BaseModel):
    """What detection found at a local connection's endpoint."""

    model_config = ConfigDict(extra="forbid")

    runtime: Runtime
    version: str | None = None
    #: The wires it serves natively (``anthropic`` / ``openai``).
    wires: list[str] = Field(default_factory=list)


__all__ = [
    "ANTHROPIC_WIRE",
    "DEFAULT_PORTS",
    "MIN_VERSIONS",
    "OPENAI_WIRE",
    "SMALL_WINDOW",
    "LocalRuntime",
    "Runtime",
    "parse_version",
    "served_wires",
]
