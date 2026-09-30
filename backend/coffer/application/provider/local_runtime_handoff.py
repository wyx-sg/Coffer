"""The prompt for setting up a local model runtime when detection finds none
(spec provider-switching "Detect a local model runtime without changing it").

Coffer only ever reads a local runtime — it never installs one, pulls a model
or starts a server. Which runtime suits this machine and which model fits its
memory are the machine's questions, so with nothing found the chore is handed
to the person's agent (``domain/handoff.py``). Every fact is Coffer's own:
the runtimes and default ports detection probes, the versions from which each
serves the agents' wires natively, and the window below which the Model tab
warns. The person presses Detect again afterwards.
"""

from __future__ import annotations

from coffer.domain.handoff import Handoff, render_handoff
from coffer.domain.provider.local_runtime import (
    ANTHROPIC_WIRE,
    DEFAULT_PORTS,
    MIN_VERSIONS,
    OPENAI_WIRE,
    SMALL_WINDOW,
    Runtime,
)

#: A runtime's name as its maker writes it.
RUNTIME_NAMES: dict[Runtime, str] = {
    Runtime.OLLAMA: "Ollama",
    Runtime.LMSTUDIO: "LM Studio",
    Runtime.VLLM: "vLLM",
    Runtime.LLAMA_SERVER: "llama.cpp's llama-server",
}

#: The two runtimes the hand-off recommends: both install as an app and find
#: a model that fits for the person.
PREFERRED = (Runtime.OLLAMA, Runtime.LMSTUDIO)


def _both_from(runtime: Runtime) -> str:
    """The first version of ``runtime`` that serves both wires."""
    minimums = [MIN_VERSIONS[runtime][wire] for wire in (ANTHROPIC_WIRE, OPENAI_WIRE)]
    known = [v for v in minimums if v is not None]
    return ".".join(str(n) for n in max(known)) if known else "any version"


def local_runtime_handoff(machine: str, memory: str | None) -> str:
    """The set-up prompt for ``machine`` (with ``memory`` when known)."""
    ports = ", ".join(
        f"{RUNTIME_NAMES[runtime]} on port {port}" for runtime, port in DEFAULT_PORTS.items()
    )
    wires = "; ".join(f"{RUNTIME_NAMES[r]} serves both from {_both_from(r)}" for r in PREFERRED)
    either = " or ".join(RUNTIME_NAMES[r] for r in PREFERRED)
    this_machine = f"This machine: {machine}" + (f", {memory} of memory." if memory else ".")
    return render_handoff(
        Handoff(
            task="Please set up a local model runtime on this machine, so Coffer can connect "
            "my agents to a model that runs here.",
            facts=(
                this_machine,
                f"Coffer looks for a runtime on its default port: {ports}. It finds vLLM "
                "only at an address I type in, because vLLM's default port is Coffer's own.",
                "Coffer connects Claude Code over the Anthropic Messages API and Codex over "
                f"the OpenAI Responses API, which the runtime must serve itself: {wires}.",
                "An agent needs a model that can call tools, and works poorly with a "
                f"context window under {SMALL_WINDOW // 1000}k tokens.",
                "No local runtime answered on those ports just now.",
            ),
            steps=(
                f"Prefer {either}; ask me which one if I have not said, and install it the "
                "way its maker recommends for this machine.",
                "Pull one chat model that can call tools and fits in this machine's memory, "
                "and tell me which one you chose and why.",
                "Leave the runtime serving on its default port, and confirm it answers "
                "there by listing its models.",
                "Then tell me to press Detect in Coffer's Add provider dialog.",
            ),
        )
    )


__all__ = ["RUNTIME_NAMES", "local_runtime_handoff"]
