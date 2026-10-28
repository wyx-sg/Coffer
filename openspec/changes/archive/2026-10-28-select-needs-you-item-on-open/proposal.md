## Why

Following a Needs you row could land on a page where the item was not
selected. A folder in Coffer's skill store that no skill claims has no skill
uid, so **Review** opened `/skills` with nothing open, and the folder sat at
the bottom of a long library. A missing secret opened the Secrets list rather
than that secret, and a stopped sync round opened the Sync page instead of its
review page. Even where the detail page was right, a row far down its list
stayed out of sight.

## What Changes

- **Every row lands on its item.** A store folder opens at
  `/skills?orphan=<name>`; a missing secret at `/secrets/<ref>` (the ref the
  action's body names); sync conflicts at `/sync/conflicts`, a first join's
  differing files at `/sync/conflicts?mode=join`, held deletions at
  `/sync/deletions`. The rest already opened their detail page.
- **The selected row scrolls into view** in the Skills, MCP servers, Channels,
  Model providers, Secrets and CLIs lists, so an item opened by address is
  visible however long the list.

## Impact

- `frontend/src/lib/overview/attention.ts`; new
  `lib/hooks/useScrollIntoViewWhenCurrent.ts`, used by the list rows.
- Spec `web-ui`, edited directly (`skip_specs: true`).
- docs-site guides `web-ui.md` and `skills.md` (en, zh). No canvas board
  changes: nothing on screen looks different, only where a row leads.
