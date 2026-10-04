## Why

The agent's Hooks tab showed Coffer's memory hook as one row per entry, and the row of a missing hook named its events as one comma-joined string ("PostToolUse,PreToolUse,SessionStart,UserPromptSubmit"). The listing already reports the hook as one hook with a set of events; the tab should read the same way.

## What Changes

- Coffer's memory-hook entries in one file become one row on the Hooks tab. Its event cell reads "Memory hook · N events" and shows a chip for each event. The row of a missing hook reads the same way.
- The tab's summary counts Coffer's hook once, and its Repair button is labelled "Repair Coffer's memory hook".
- New en and zh strings for the row label.

## Capabilities

### New Capabilities

### Modified Capabilities
- `agent-registry`: how the Hooks tab shows Coffer's memory hook.

## Impact

- Frontend: `lib/agents/hookRows.ts`, `components/agents/AgentHooksTab.tsx`, the new `AgentHookEventCell.tsx`, `AgentHookRowActions.tsx`, `i18n/locales/{en,zh}.json`.
- Docs: the Hooks section of the agents guide.
- Design canvas: the Agents canvas's Hooks-tab boards.
