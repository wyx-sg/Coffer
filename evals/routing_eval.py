"""Tool-routing eval — does the model pick the right Coffer tool?

Given Coffer's tool catalogue (name + description) and a natural-language
request, the model chooses the single best tool; the choice is graded against a
golden expected tool.

Because tool selection is non-deterministic, each case is sampled ``k`` times
and reported as **accuracy** (mean correctness over all samples) and **pass^k**
(fraction of cases the model gets right on *every* attempt — the reliability bar
for a production agent), alongside **pass@k** (right at least once).

The model is pluggable. It defaults to a local Ollama model to keep the suite
free, but any OpenAI-compatible endpoint works — point it elsewhere with the
``COFFER_EVAL_*`` environment variables (see ``_resolve_model``). If the server
is unreachable the suite returns ``None`` (skipped) rather than failing.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from evals._io import load_jsonl


@dataclass(frozen=True)
class ModelSpec:
    """Where to send generation requests and how to talk to it."""

    provider: str  # "ollama" | "openai"
    model: str
    base_url: str
    api_key: str | None = None


def _resolve_model() -> ModelSpec:
    """Build the model spec from ``COFFER_EVAL_*`` env vars (Ollama defaults)."""
    provider = os.environ.get("COFFER_EVAL_PROVIDER", "ollama").lower()
    model = os.environ.get("COFFER_EVAL_MODEL") or os.environ.get(
        "OLLAMA_MODEL", "qwen2.5:0.5b"
    )
    default_base = (
        "http://localhost:11434" if provider == "ollama" else "https://api.openai.com"
    )
    base_url = (
        os.environ.get("COFFER_EVAL_BASE_URL")
        or os.environ.get("OLLAMA_URL")
        or default_base
    ).rstrip("/")
    return ModelSpec(
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=os.environ.get("COFFER_EVAL_API_KEY"),
    )


def parse_tool_choice(response: str, valid_names: list[str]) -> str | None:
    """Extract the chosen tool name from a free-form model response.

    Returns the valid tool whose name appears earliest in the response
    (case-insensitive), or ``None`` if no known tool is mentioned. Longer names
    win ties so ``list_knowledge_bases`` isn't shadowed by a shorter prefix.
    """
    text = response.lower()
    best: tuple[int, int, str] | None = None  # (position, -len, name)
    for name in valid_names:
        pos = text.find(name.lower())
        if pos == -1:
            continue
        candidate = (pos, -len(name), name)
        if best is None or candidate < best:
            best = candidate
    return best[2] if best else None


def aggregate_routing(cases: list[dict], *, samples: int) -> dict:
    """Aggregate per-case results into accuracy / pass^k / pass@k (pure)."""
    n = len(cases)
    total = n * samples
    correct = sum(c["correct_count"] for c in cases)
    return {
        "accuracy": round(correct / total, 4) if total else 0.0,
        "pass^k": round(sum(1 for c in cases if c["correct_count"] == samples) / n, 4)
        if n
        else 0.0,
        "pass@k": round(sum(1 for c in cases if c["correct_count"] >= 1) / n, 4)
        if n
        else 0.0,
    }


def _build_prompt(catalog: list[dict], request: str) -> str:
    lines = [
        "You are a tool router. Choose the single best tool for the user's request.",
        "",
        "Tools:",
    ]
    for tool in catalog:
        lines.append(f"- {tool['name']}: {tool['description']}")
    lines += [
        "",
        f"User request: {request}",
        "",
        "Reply with ONLY the tool name, nothing else.",
    ]
    return "\n".join(lines)


def _generate(
    prompt: str, *, spec: ModelSpec, temperature: float, timeout: float
) -> str:
    """Generate a completion via Ollama or an OpenAI-compatible endpoint."""
    if spec.provider == "ollama":
        body = {
            "model": spec.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        url = f"{spec.base_url}/api/generate"
        headers = {"Content-Type": "application/json"}
        key = "response"
    else:  # OpenAI-compatible chat completions (OpenAI, LM Studio, vLLM, ...)
        body = {
            "model": spec.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        url = f"{spec.base_url}/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        if spec.api_key:
            headers["Authorization"] = f"Bearer {spec.api_key}"

    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — operator-configured
        data = json.loads(resp.read())
    if spec.provider == "ollama":
        return data[key]
    return data["choices"][0]["message"]["content"]


def run_routing_eval(
    *, samples: int = 3, temperature: float = 0.3, timeout: float = 60.0
) -> dict | None:
    """Run the tool-routing suite; return a scorecard dict, or None if skipped."""
    spec = _resolve_model()
    catalog = load_jsonl("tool_catalog.jsonl")
    cases = load_jsonl("tool_routing.jsonl")
    valid = [t["name"] for t in catalog]

    results: list[dict] = []
    for case in cases:
        prompt = _build_prompt(catalog, case["request"])
        chosen: list[str | None] = []
        for _ in range(samples):
            try:
                raw = _generate(
                    prompt, spec=spec, temperature=temperature, timeout=timeout
                )
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
                return None  # model server unreachable -> skip the whole suite
            chosen.append(parse_tool_choice(raw, valid))
        correct_count = sum(1 for c in chosen if c == case["expected_tool"])
        results.append(
            {
                "request": case["request"],
                "expected": case["expected_tool"],
                "choices": chosen,
                "correct_count": correct_count,
            }
        )

    agg = aggregate_routing(results, samples=samples)
    return {
        "suite": "routing",
        "primary": {"name": "accuracy", "value": agg["accuracy"]},
        "secondary": {
            "provider": spec.provider,
            "model": spec.model,
            "samples": samples,
            "pass^k": agg["pass^k"],
            "pass@k": agg["pass@k"],
        },
        "n": len(results),
        "cases": results,
    }
