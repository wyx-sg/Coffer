# ADR-044: OpenClaw is the sixth managed leaf agent

> 中文版: [ADR-044-openclaw-managed-agent.zh.md](ADR-044-openclaw-managed-agent.zh.md)

**Status**: Accepted
**Date**: 2026-07-10
**Deciders**: Yuxing Wu
**Related**: reverses the openclaw verdict of [ADR-040](ADR-040-re-widen-agent-registry.md); completes the correction begun by [ADR-042](ADR-042-context-injection-mechanisms.md) and recorded in [`docs/research/openclaw-gateway-integration.md`](../research/openclaw-gateway-integration.md); spec `004-agent-registry` (FR-003/FR-003a/FR-013/FR-046/FR-048), spec `008-agent-chat` (agent providers), spec `011-provider-switching` (projection)

## Context

[ADR-040](ADR-040-re-widen-agent-registry.md) re-added `opencode` / `hermes` /
`cursor` as managed agents but kept **openclaw** out: "a peer gateway, not a
leaf", with a five-row capability table declaring four facets N/A. ADR-042's
first-principles re-check found **three of those five rows wrong** (MCP IS
injectable, native memory IS disableable, skills ARE drop-in), and the research
note reversed the conclusion — *openclaw IS a viable managed leaf agent* —
"pending a real install to verify against."

That install now exists (openclaw **2026.6.11**, onboarded, on PATH), and every
capability claim below was probed against it — per the ADR-042 discipline that
each matrix cell cites a doc or a probe, never an assumption.

## Probe-verified capability matrix

| Facet | Mechanism | Evidence |
| --- | --- | --- |
| Chat adapter (spec 008) | `openclaw agent --agent main --session-key <key> -m <text> --json --local` → stdout is ONE clean JSON blob (`payloads[].text`, `finalAssistantVisibleText`, `stopReason`, `completion.finishReason`, `executionTrace.winnerProvider/winnerModel`); logs on stderr. **Non-streaming** — Coffer's first such provider. `--local` = fully embedded, no gateway daemon needed, plugin registry preloaded per run. Same `--session-key` → same session. | live turn, 2026.6.11 |
| Coffer-MCP inject (FR-019) | `mcp.servers.<name>` in `~/.openclaw/openclaw.json` (plain JSON), `{command, args?, env?, enabled?}` command-map. The container is **nested** — the manifest's `container_key` is the dotted path `mcp.servers` and the JSON transforms descend one object per dot. CAUTION: openclaw rejects interpreter-startup env keys (`NODE_OPTIONS`, `PYTHONPATH`, …) inside a server's `env` at config load; Coffer's entry carries no env. | scratch-config probe: `openclaw mcp status` lists a hand-written `coffer: stdio` entry |
| Session-context injection (FR-043/044/048) | `PLUGIN_DROP`, **openclaw flavor**: a package dir `extensions/coffer-session-context/` (`package.json` with `openclaw.extensions`, `openclaw.plugin.json` `{id, configSchema}`, `index.js` exporting `definePluginEntry`) PLUS `plugins.entries.<id>.enabled: true` — non-bundled plugins are **fail-closed**. Hook: `api.on("before_prompt_build", h)`; handler returns `{appendSystemContext}`. Plugins run in-process at full privilege → can spawn `coffer-hook`. | `openclaw config validate` accepts the package + flag pair; live plugin-injection turn (see Consequences) |
| Provider projection (spec 011) | `models.providers.coffer = {api, baseUrl, apiKey, models}`; `apiKey` supports `${UPPERCASE_VAR}`; model refs `provider/model`; active model via `agents.defaults.model.primary` (user `fallbacks` preserved). `models` is REQUIRED for a custom provider and each entry needs both `id` and `name`; `models: []` is valid (the unbound-agent projection). openclaw speaks BOTH `openai-completions` and `anthropic-messages` `api` values. | `openclaw config validate` probes for each shape, 2026-07-10 |
| Missing-key degradation | A missing env var behind `apiKey: "${COFFER_PROVIDER_KEY}"` is a startup **WARNING** only ("Missing env var … feature using this value will be unavailable"), exit 0, other providers unaffected — this **overrides the docs' "throws at config load" claim** and is what makes codex-style projection viable: persist the reference, inject the key per Coffer-driven turn, and a user-run openclaw without the var degrades gracefully. | probe 2026-07-10 |
| Native-memory disable (FR-046) | `plugins.slots.memory: "none"` empties the memory plugin slot; restore = remove the key. | `openclaw config validate` accepts it |
| Skills (spec 005) | `~/.openclaw/skills/<name>/SKILL.md`; SYMLINKED skill folders ARE discovered — Coffer's existing `FOLDER` delivery works unchanged. | live discovery probe |
| Detection | Default marker `~/.openclaw` (env overrides like `OPENCLAW_STATE_DIR` exist and are treated like every other agent's non-default dir: not resolved). | install layout |

## Decision

1. **`AgentType.OPENCLAW = "openclaw"` is re-added** with one `AgentDescriptor`
   record — no DB migration (re-adding an enum value the `0031` migration
   deleted; old rows were already purged).
2. **The chat adapter is non-streaming**: spawn per turn, read stdout to EOF,
   parse the one blob, emit `TurnStarted` → one `TextDelta` → `TurnDone`
   (`executionTrace` winner stamps the assistant message). The upstream session
   is pinned by a Coffer-derived `--session-key coffer-<conversation_id>` —
   nothing is discovered from the stream or persisted per turn.
3. **No cwd semantics.** openclaw is a personal-assistant gateway, not a
   repo-scoped coding CLI: `openclaw agent` has no cwd flag and runs in the
   agent's own workspace (`agents.defaults.workspace`). The provider therefore
   **ignores** the conversation's cwd (documented, not validated) instead of
   pretending the turn is project-scoped.
4. **MCP injection extends the JSON transforms with a dotted container path**
   (`mcp.servers`) rather than adding a new entry style — the entry itself is
   the plain command-map Claude Code uses.
5. **Session context ships as a second `PluginFlavor`** (`OPENCLAW`) of the
   existing `PLUGIN_DROP` mode: three rendered package files plus the
   fail-closed `plugins.entries` enable flag (`plugin_enable_config_key` on the
   spec keeps the hook service generic). Uninstall removes the whole package
   with **no `.bak`** — the content is Coffer-rendered and regenerates
   byte-identically, and a leftover backup package would still be discovered by
   openclaw's extension scanner — and removes the enable flag (the config file
   write keeps its usual `.bak`).
6. **Provider projection is codex-style** (`${COFFER_PROVIDER_KEY}` reference on
   disk, key injected into the subprocess env per Coffer-driven turn), keyed by
   the connection's wire: `openai` → `api: "openai-completions"`, `anthropic` →
   `api: "anthropic-messages"`. openclaw joins BOTH wires' default
   compatible-agents sets.
7. **Native memory disable** wires `plugins.slots.memory: "none"` into the
   existing FR-046 toggle.
8. **Config-file allowlist**: `openclaw.json` (key `config`) + the six workspace
   instruction files (`instructions`/`soul`/`identity`/`user`/`tools`/`memory`,
   paths assuming the default `~/.openclaw/workspace`) + the `extensions/`
   directory entry.

## Consequences

- Coffer gains its first **non-streaming** chat provider; the chat surface
  shows the whole reply at once. No timeout is added on Coffer's side
  (openclaw's own `--timeout` default governs the turn).
- **Gateway-restart caveat**: `--local` embedded runs (all Coffer-driven turns)
  preload the plugin registry per run and see the dropped extension
  immediately; a long-running `openclaw gateway` (channel-driven use) picks it
  up only after a restart. Documented in spec FR-048.
- openclaw remains *also* a peer gateway (it orchestrates coding CLIs and hosts
  channels). Coffer manages its leaf-agent surface only; the
  gateway-as-LLM-endpoint integration sketched in the research note stays
  available and unaffected. Note the inheritance effect ADR-040 identified is
  now a feature: Coffer's writes to `~/.claude/` etc. are inherited by
  openclaw-spawned sub-workers.
- The e2e verification for this slice: a live `--local` turn with the dropped
  extension + a stub `coffer-hook` confirmed the injected marker reaches the
  model (the model repeated it back), and the adapter parsed a real
  `--json` blob end-to-end.

## Alternatives considered

- **Keep openclaw out; integrate only as an OpenAI-compatible LLM connection**
  (ADR-040's verdict). Rejected: three of the five capability claims behind it
  were wrong, and the corrected matrix shows full leaf-facet parity. The
  connection-style integration remains possible *in addition* — the two do not
  compete.
- **A new `McpEntryStyle` for the nested container.** Rejected: the entry shape
  is the existing command-map; only the container location differs, and a
  dotted `container_key` is data, not machinery.
- **Uninstall keeps a `.bak` of the extension package.** Rejected: openclaw
  scans `extensions/` for package dirs, so a `.bak` package would still be
  discovered (as a disabled, stale-id extension); the package is fully
  Coffer-rendered and reinstall regenerates it byte-identically.
