## Why

An API-key connection reached an agent by being written into the agent's own config: Claude Code got the upstream base URL and a helper that printed the real key, and Codex got the upstream base URL with the real key in the environment of every Codex process Coffer started. Three things the 1.0 plan needs cannot be done from a config file. Usage and cost of API-key traffic cannot be metered, because nothing Coffer runs sees the requests. A connection cannot fail over, because nothing is in the request path. And the real key stays within the agent's reach: `coffer provider key` printed it, and Codex's environment held it (ADR only-a-present-human-sees-a-secret-or-sends-it-somewhere-new). A Codex started from the user's own terminal had no key unless the user exported it.

## What Changes

- **Local model proxy.** A separate process, started from the daemon's binary (`coffer-daemon proxy`) and supervised by the daemon, bound to `127.0.0.1` on a fixed port (8001 by default, `proxy_port` in `daemon-config.json`). It relays Anthropic Messages and OpenAI Responses byte for byte to an upstream of the same wire, injects the connection's key, and fails over to another connection serving the same model only before the first content byte. It refuses a foreign `Host`, any `Origin`, and any credential that is not a Coffer proxy token. It logs metadata only. It survives daemon restarts; the daemon re-attaches to it through `~/.coffer/proxy.json`.
- **Per-agent local tokens.** Each agent has its own 256-bit token. `coffer proxy token --agent-uid <uid>` prints it, `coffer proxy rotate <agent>` replaces it, and `coffer proxy status` reports the proxy. The token is kept in the credential store under a machine-local ref that sync never carries.
- **Projection through the proxy.** Claude Code's `ANTHROPIC_BASE_URL` points at the proxy's `/anthropic` route. Its `apiKeyHelper` prints the agent's token, and `NO_PROXY` covers loopback. Codex's provider block points at `/openai/v1` with `supports_websockets = false`, `requires_openai_auth = false` and a command-backed `auth`. `env_key` and the `COFFER_PROVIDER_KEY` shell exclusion go away, and Coffer puts no key into any Codex process's environment. Switching between two API-key connections changes the proxy's route, not the agent's file.
- **Removed:** `coffer provider key`, `GET /api/v1/providers/{uid}/key` and `GET /api/v1/providers/active-key/{wire}`. No route or command returns a provider key.
- **Local model connections.** A keyless connection to a runtime on this machine (Ollama, LM Studio, vLLM, llama-server) uses its native protocol and goes through the proxy. It is detected read-only by `coffer provider detect-local` / `POST /api/v1/providers/detect-local`, with minimum versions per wire, and created with `coffer provider add … --local`.

## Capabilities

### New Capabilities

### Modified Capabilities
- `provider-switching`: the projection points agents at the proxy; the proxy's relay, tokens, Host/Origin refusal and failover; local model connections and their detection; the key command and routes are removed.
- `daemon`: the daemon supervises the proxy.

## Impact

- Backend: new `infrastructure/model_proxy/` (relay, ASGI surface, member health, spool, entry, supervisor), `domain/model_proxy/state.py`, `domain/usage/{records,stream_usage}.py`, `domain/provider/local_runtime.py`, `infrastructure/provider/local_runtime.py`, `application/provider/{proxy_tokens,proxy_state}.py`, `surfaces/http/{model_proxy_wiring,proxy_routes,proxy_dependencies}.py`, `surfaces/cli/proxy_cmd.py`. Changed: the projector and projection transforms, provider service/routes/CLI, the chat providers (no key injection), sync credential listing, and daemon entry (proxy mode).
- Principles: the Credentials clause names the proxy as a header-injection consumer that holds decrypted provider keys in memory. The process model gains the proxy as the daemon's only sibling process.
- Docs: the Model proxy architecture page, the providers guide, the security page, and the CLI/REST references. The proxy ADR's failover paragraph now describes a pool of connections rather than keys of one connection, and records the minimum Codex version.
