"""Read-only detection of a local model runtime (spec provider-switching
"Detect a local model runtime without changing it").

Every probe is a GET (or Ollama's read-only ``POST /api/show``) against a
loopback address: nothing is pulled, loaded or downloaded, and a non-loopback
URL is refused before anything is sent. The fingerprint decides the runtime,
never the port — 8080 is shared by llama-server and mlx_lm.server, and vLLM's
default 8000 is Coffer's own daemon port.

What is read per model is the window the runtime actually SERVES where it says
(Ollama ``/api/ps`` once a model is loaded, LM Studio's loaded instance,
llama-server ``/props``, vLLM ``max_model_len``) and whether it can call tools.
A value the runtime does not report stays ``None``; the Model tab asks for it.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from coffer.domain.model_proxy.state import upstream_root
from coffer.domain.provider.local_runtime import (
    DEFAULT_PORTS,
    LocalRuntime,
    Runtime,
    served_wires,
)

_TIMEOUT = httpx.Timeout(3.0)


class NotLoopbackError(ValueError):
    """Detection only ever probes this machine."""


@dataclass(frozen=True)
class LocalModel:
    id: str
    context_window: int | None = None
    tools: bool | None = None


@dataclass(frozen=True)
class Detection:
    base_url: str
    runtime: LocalRuntime
    models: list[LocalModel] = field(default_factory=list)


def _require_loopback(base_url: str) -> str:
    parsed = urlparse(base_url if "://" in base_url else f"http://{base_url}")
    host = (parsed.hostname or "").lower()
    ok = host == "localhost"
    if not ok:
        try:
            ok = ipaddress.ip_address(host).is_loopback
        except ValueError:
            ok = False
    if not ok:
        raise NotLoopbackError(f"{base_url} is not a loopback address")
    return upstream_root(f"{parsed.scheme or 'http'}://{parsed.netloc}{parsed.path}")


async def _json(client: httpx.AsyncClient, method: str, url: str, **kw: Any) -> Any:
    try:
        r = await client.request(method, url, **kw)
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except ValueError:
        return None


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


async def _ollama(c: httpx.AsyncClient, root: str) -> Detection | None:
    version = await _json(c, "GET", f"{root}/api/version")
    if not isinstance(version, dict) or "version" not in version:
        return None
    tags = await _json(c, "GET", f"{root}/api/tags") or {}
    loaded = await _json(c, "GET", f"{root}/api/ps") or {}
    served = {
        m.get("name"): _int(m.get("context_length"))
        for m in loaded.get("models", [])
        if isinstance(m, dict)
    }
    models: list[LocalModel] = []
    for m in tags.get("models", []):
        name = m.get("name") if isinstance(m, dict) else None
        if not isinstance(name, str):
            continue
        show = await _json(c, "POST", f"{root}/api/show", json={"model": name}) or {}
        caps = show.get("capabilities")
        tools = ("tools" in caps) if isinstance(caps, list) else None
        models.append(LocalModel(id=name, context_window=served.get(name), tools=tools))
    rt = LocalRuntime(
        runtime=Runtime.OLLAMA,
        version=str(version["version"]),
        wires=served_wires(Runtime.OLLAMA, str(version["version"])),
    )
    return Detection(root, rt, models)


async def _lmstudio(c: httpx.AsyncClient, root: str) -> Detection | None:
    payload = await _json(c, "GET", f"{root}/api/v1/models")
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
        return None
    models: list[LocalModel] = []
    for m in payload["models"]:
        if not isinstance(m, dict) or not isinstance(m.get("key"), str):
            continue
        window = None
        for inst in m.get("loaded_instances") or []:
            window = _int((inst.get("config") or {}).get("context_length")) or window
        caps = m.get("capabilities") or {}
        tools = caps.get("trained_for_tool_use") if isinstance(caps, dict) else None
        models.append(LocalModel(id=m["key"], context_window=window, tools=tools))
    # The native REST API exists from 0.4.0 and reports no version; the
    # Messages wire needs 0.4.1, so only Responses (0.3.29) is certain.
    rt = LocalRuntime(runtime=Runtime.LMSTUDIO, version=None, wires=["openai"])
    return Detection(root, rt, models)


async def _llama_server(c: httpx.AsyncClient, root: str) -> Detection | None:
    listing = await _json(c, "GET", f"{root}/v1/models")
    data = listing.get("data") if isinstance(listing, dict) else None
    if not isinstance(data, list) or not any(
        isinstance(m, dict) and m.get("owned_by") == "llamacpp" for m in data
    ):
        return None
    props = await _json(c, "GET", f"{root}/props") or {}
    window = _int((props.get("default_generation_settings") or {}).get("n_ctx"))
    models = [LocalModel(id=str(m.get("id")), context_window=window) for m in data if m.get("id")]
    rt = LocalRuntime(
        runtime=Runtime.LLAMA_SERVER,
        version=None,
        wires=served_wires(Runtime.LLAMA_SERVER, None),
    )
    return Detection(root, rt, models)


async def _vllm(c: httpx.AsyncClient, root: str) -> Detection | None:
    version = await _json(c, "GET", f"{root}/version")
    if not isinstance(version, dict) or "version" not in version:
        return None
    listing = await _json(c, "GET", f"{root}/v1/models") or {}
    models = [
        LocalModel(id=str(m["id"]), context_window=_int(m.get("max_model_len")))
        for m in listing.get("data", [])
        if isinstance(m, dict) and m.get("id")
    ]
    v = str(version["version"])
    rt = LocalRuntime(runtime=Runtime.VLLM, version=v, wires=served_wires(Runtime.VLLM, v))
    return Detection(root, rt, models)


_PROBES = (_ollama, _lmstudio, _llama_server, _vllm)


async def detect(base_url: str) -> Detection | None:
    """What runtime answers at ``base_url`` (loopback only), or ``None``."""
    root = _require_loopback(base_url)
    async with httpx.AsyncClient(timeout=_TIMEOUT, trust_env=False) as client:
        for probe in _PROBES:
            found = await probe(client, root)
            if found is not None:
                return found
    return None


async def detect_defaults() -> list[Detection]:
    """Probe each runtime's default loopback port."""
    found: list[Detection] = []
    for port in sorted(set(DEFAULT_PORTS.values())):
        hit = await detect(f"http://127.0.0.1:{port}")
        if hit is not None:
            found.append(hit)
    return found


__all__ = ["Detection", "LocalModel", "NotLoopbackError", "detect", "detect_defaults"]
