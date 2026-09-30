# Tasks

## 1. Backend
- [x] 1.1 `HttpApiTransport` / `HttpApiTool` / `OpenApiSource` in `domain/mcp/http_api.py`; request rendering (path, query, body, headers) and save-time validation
- [x] 1.2 `domain/mcp/openapi_import.py`: operations → draft tools, suggested base URL and auth, re-import diff
- [x] 1.3 `infrastructure/mcp/http_api_client.py`: the in-process upstream (initialize, tools/list with annotations, tools/call over httpx with timeout, no redirects, 1 MiB cap, masking); factory branch; secret target `http_api <base_url>`
- [x] 1.4 Annotations passed through discovery into the gateway's listing
- [x] 1.5 Per-tool gate (`gateway_tool_gate.py`): switched-off and override-excluded tools left out of `tools/list` and search, refused on call as `denied`
- [x] 1.6 Migration 0115 `mcp_tool_reach` and its repo; overrides deleted with their tool and group
- [x] 1.7 OpenAPI fetch from a URL through the SSRF guard (5 MiB, 20 s); YAML/JSON parse
- [x] 1.8 `CustomToolService`: create / read / change / delete groups and tools, reach overrides, health and 24-hour summary, test, import and re-import
- [x] 1.9 REST `/api/v1/custom-tools…` with Pydantic models; `OWNERS` entry; `make contracts`
- [x] 1.10 CLI `coffer tool` and `coffer tool op`, approvals exit 9 / `--wait`; parity table

## 2. Frontend
- [x] 2.1 `/custom-tools` and `/custom-tools/<group>` (list by health, group page, tools table, drawer editor with Test), Add custom tool flow, New group dialog, first run
- [x] 2.2 MCP servers list and Add dialog leave `http_api` servers out; their MCP-server address redirects to the group page

## 3. Tests
- [x] 3.1 Unit: rendering, validation, OpenAPI reading and re-import diff, annotations
- [x] 3.2 Integration: fake HTTP upstream through the gateway (prefix, secret, masking, cap, redirect, error status, timeout), per-tool gate, boundary approvals, REST and CLI, re-import
- [x] 3.3 acceptance(mcp-gateway, …) for every scenario of this change
- [x] 3.4 Vitest for the pages; e2e for the Custom tools page; visual baselines

## 4. Docs
- [x] 4.1 `docs-site/guides/custom-tools.md`; architecture notes in `mcp-gateway.md` and `security.md` (outbound requests); CLI and REST references regenerated; mcp-gateway `data-model.md`

## 5. Verify and archive
- [x] 5.1 `make verify`, `make verify-e2e`, `make verify-visual`
- [x] 5.2 Archive the change
