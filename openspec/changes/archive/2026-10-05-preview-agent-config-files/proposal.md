## Why

An agent's Config files tab lists `settings.json`, `.claude.json`, `CLAUDE.md`,
`config.toml` and the subagent files, but shows none of them: reading what an
agent is configured with means leaving Coffer for an editor. Knowledge
documents, memories, skill files and the agent's own memory store all preview
in Coffer and hand only editing to the editor. Config files should read the
same way: viewing in Coffer, editing in the person's editor.

## What Changes

- **Preview route**: `GET /api/v1/agents/{uid}/config-files/{key}/content`
  (`?child=<relpath>` under a directory entry, limited to the files the listing
  returns) answers the file's text as written for a read-only preview, read up
  to 1 MiB, with its absolute path, format, size, `truncated` and `binary`.
- **Web UI**: on the Config files tab a file's name opens a dialog with the
  shared read-only viewer (Preview / Source for Markdown, Open in editor,
  Reveal in Finder). Rows keep
  Open in editor and Reveal in Finder. No edit, save, new file or delete.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-registry`: a config file's read-only preview; the Config files tab
  opens it from a row's name.
- `agent-registry/codex`: the credential-file rule names the preview route.

## Impact

- Backend: `domain/agent/config_files.py` (`FileText`),
  `infrastructure/agent/config_file_store.py` (`read_preview`),
  `application/agent/config_file_service.py` (`read_preview`),
  `surfaces/http/agent_config_routes.py` (the route).
- Frontend: `components/agents/AgentConfigFilesTab.tsx`, a preview dialog,
  `lib/api/agents.ts`, `lib/hooks/useAgents.ts`, i18n.
- Docs: `docs-site/guides/agents.md` (+ zh).
- Canvas: Agents canvas, Config files boards (2.1.40–2.1.48) gain the preview
  dialog.
