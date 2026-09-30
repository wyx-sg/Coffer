"""Local model runtimes: read-only detection and keyless connections (spec
provider-switching "Detect a local model runtime without changing it",
"Configure a local model connection"), against a fake Ollama on loopback."""

from __future__ import annotations

import json
import socket

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from tests.integration.model_proxy.harness import ServerThread
from tests.integration.surfaces.http.test_provider_routes import (
    _agent_dir,
    _app,
    _client,
    _register_agent,
)


def _fake_ollama(version: str, calls: list[str]) -> Starlette:
    """Ollama's read-only endpoints; anything that would change it is recorded
    so a test can say none was called."""

    async def version_(request: Request) -> JSONResponse:
        calls.append("GET /api/version")
        return JSONResponse({"version": version})

    async def tags(request: Request) -> JSONResponse:
        calls.append("GET /api/tags")
        return JSONResponse({"models": [{"name": "qwen3-coder"}, {"name": "embed-only"}]})

    async def ps(request: Request) -> JSONResponse:
        calls.append("GET /api/ps")
        return JSONResponse({"models": [{"name": "qwen3-coder", "context_length": 65536}]})

    async def show(request: Request) -> JSONResponse:
        body = await request.json()
        calls.append(f"POST /api/show {body['model']}")
        caps = ["completion", "tools"] if body["model"] == "qwen3-coder" else ["embedding"]
        return JSONResponse({"capabilities": caps})

    async def mutate(request: Request) -> JSONResponse:
        calls.append(f"{request.method} {request.url.path}")
        return JSONResponse({}, status_code=500)

    return Starlette(
        routes=[
            Route("/api/version", version_),
            Route("/api/tags", tags),
            Route("/api/ps", ps),
            Route("/api/show", show, methods=["POST"]),
            Route("/api/pull", mutate, methods=["POST"]),
            Route("/api/generate", mutate, methods=["POST"]),
        ]
    )


@pytest.mark.acceptance(
    spec="provider-switching", scenario="detection reads the runtime, version and served windows"
)
def test_detection_reads_runtime_version_and_windows(tmp_path, monkeypatch):
    calls: list[str] = []
    with ServerThread(_fake_ollama("0.14.2", calls), lifespan="off") as ollama:
        app = _app(tmp_path, monkeypatch, 59871)
        with _client(app) as c:
            r = c.post("/api/v1/providers/detect-local", json={"base_url": ollama.base})
    assert r.status_code == 200, r.text
    (hit,) = r.json()["found"]
    assert hit["runtime"] == {
        "runtime": "ollama",
        "version": "0.14.2",
        "wires": ["anthropic", "openai"],
    }
    models = {m["id"]: m for m in hit["models"]}
    assert models["qwen3-coder"] == {"id": "qwen3-coder", "context_window": 65536, "tools": True}
    assert models["embed-only"]["tools"] is False
    # A runtime answered, so there is nothing to hand off.
    assert r.json()["handoff"] is None
    # Read-only: nothing that pulls, loads or generates was called.
    assert not any("pull" in call or "generate" in call for call in calls)


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a runtime below the minimum version serves no wire it lacks",
)
def test_an_old_runtime_serves_only_the_wires_it_has(tmp_path, monkeypatch):
    with ServerThread(_fake_ollama("0.13.5", []), lifespan="off") as ollama:
        app = _app(tmp_path, monkeypatch, 59872)
        with _client(app) as c:
            r = c.post("/api/v1/providers/detect-local", json={"base_url": ollama.base})
    assert r.json()["found"][0]["runtime"]["wires"] == ["openai"]


@pytest.mark.acceptance(
    spec="provider-switching", scenario="detection refuses a non-loopback address"
)
def test_detection_refuses_a_remote_address(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59873)
    with _client(app) as c:
        r = c.post("/api/v1/providers/detect-local", json={"base_url": "http://example.com:11434"})
    assert r.status_code == 422, r.text


@pytest.mark.acceptance(
    spec="provider-switching", scenario="nothing found hands setting up a runtime to an agent"
)
def test_nothing_found_hands_setting_up_a_runtime_to_an_agent(tmp_path, monkeypatch):
    with socket.socket() as probe:  # a loopback port nothing listens on
        probe.bind(("127.0.0.1", 0))
        silent = probe.getsockname()[1]
    app = _app(tmp_path, monkeypatch, 59876)
    with _client(app) as c:
        r = c.post(
            "/api/v1/providers/detect-local", json={"base_url": f"http://127.0.0.1:{silent}"}
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["found"] == []
    prompt = body["handoff"]["prompt"]
    # The machine, the runtimes detection probes with their default ports, and
    # the two it recommends — never an install command.
    assert "This machine:" in prompt
    for fact in ("Ollama on port 11434", "LM Studio on port 1234", "llama-server on port 8080"):
        assert fact in prompt
    assert "Prefer Ollama or LM Studio" in prompt
    assert "press Detect" in prompt
    assert "brew" not in prompt and "curl " not in prompt
    # The rules every hand-off carries.
    assert "sudo or changes system settings" in prompt


@pytest.mark.acceptance(
    spec="provider-switching", scenario="create a keyless local runtime connection"
)
def test_create_a_keyless_local_runtime_connection(tmp_path, monkeypatch):
    with ServerThread(_fake_ollama("0.14.2", []), lifespan="off") as ollama:
        app = _app(tmp_path, monkeypatch, 59874)
        cfg = _agent_dir(tmp_path)
        with _client(app) as c:
            cc = _register_agent(c, agent_type="claude_code", config_dir=cfg)
            found = c.post("/api/v1/providers/detect-local", json={"base_url": ollama.base})
            hit = found.json()["found"][0]
            r = c.post(
                "/api/v1/providers",
                json={
                    "name": "ollama",
                    "protocol": "anthropic",
                    "base_url": ollama.base,
                    "local_runtime": hit["runtime"],
                    "models": [
                        {"id": m["id"], "context_window": m["context_window"]}
                        for m in hit["models"]
                        if m["tools"] is not False
                    ],
                },
            )
            assert r.status_code == 201, r.text
            body = r.json()
            assert body["secret_ref"] is None
            assert body["local_runtime"]["runtime"] == "ollama"
            assert [m["id"] for m in body["models"]] == ["qwen3-coder"]
            assert body["models"][0]["context_window"] == 65536

            c.patch(f"/api/v1/agents/{cc}", json={"model": "qwen3-coder"})
            assert c.post(f"/api/v1/providers/{body['uid']}/activate").status_code == 200
    settings = json.loads((cfg / "settings.json").read_text())
    assert settings["env"]["CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS"] == "1"
    assert settings["env"]["CLAUDE_CODE_MAX_CONTEXT_TOKENS"] == "65536"
    assert settings["env"]["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:8001/anthropic"


@pytest.mark.acceptance(
    spec="provider-switching", scenario="a local runtime connection must be on this machine"
)
def test_a_local_runtime_must_be_on_this_machine(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59875)
    with _client(app) as c:
        r = c.post(
            "/api/v1/providers",
            json={
                "name": "remote",
                "protocol": "openai",
                "base_url": "https://gpu.example.com/v1",
                "local_runtime": {"runtime": "vllm", "version": "0.30.0", "wires": ["openai"]},
            },
        )
    assert r.status_code == 422, r.text
