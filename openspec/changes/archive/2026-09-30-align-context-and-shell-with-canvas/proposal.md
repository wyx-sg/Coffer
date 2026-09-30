## Why

The final design for Knowledge, Memory and the app shell settled a few behaviours the code does not have yet: automatic upkeep is controlled from the page it upkeeps rather than from Settings, a deleted knowledge collection can be brought back from history, a collection has no title of its own, the Knowledge inbox never becomes a sidebar badge, and the command palette only jumps.

## What Changes

- Knowledge carries an **Automatic** control in its header: a popover with the curation switch, the interval, Curate now, when the last pass ran and the next one will, and — once the vault spans several machines — which Mac runs curation.
- Memory carries the same control for reading the agents' memory automatically: a switch and an interval, with the last and next read.
- Settings › General keeps only Coffer's model; the upkeep rows and the curation owner line leave it.
- A deleted collection is listed in Recent changes with **Restore**, which brings the folder back from the vault's history.
- A collection has no title: its heading is its folder name, with an editable description.
- The sidebar shows no badge for items waiting in a Knowledge inbox; the Inbox node's count in the tree is the only signal.
- The command palette offers pages and objects only.
- Each unattended pass reports when it last ran and runs next; the Memory page says when the agents' memory was last read, whose read failed, and how far Update memory is.
- Overview's Ignore is kept by the daemon on this machine, so the sidebar, the menu bar and Overview count the same items; a memory hook changed by hand that Coffer could not rewrite opens the agent's Hooks tab.
- Lists load N more instead of paging; an unknown address suggests the closest page; a found update shows a card above the sidebar footer; language and theme live in the version menu.
- Knowledge, Memory, the shell and Overview follow the final boards in layout and copy.

## Capabilities

### New Capabilities

### Modified Capabilities
- `knowledge`: restore a deleted collection from history; a collection has no title; the page's upkeep control.
- `memory`: the page's automatic-reading control.
- `internal-engine`: the upkeep switches and the curation owner are shown and changed on the Knowledge and Memory pages, not in Settings › General.
- `web-ui`: no sidebar badge for the Knowledge inbox; the palette jumps only; the version menu, update card, closest-page 404, Overview's hook row and daemon-kept Ignore.
- `resource-framework`: `knowledge` joins the kinds without a title.

## Impact

- Frontend: Knowledge and Memory pages, the shell, the palette, Overview, shared components; Settings › General loses the upkeep card.
- Backend: the knowledge restore and description routes and CLI; the upkeep, memory-reading and attention-ignore routes; migrations 0133 (collection titles) and 0134 (attention ignores).
- Docs: the Knowledge, Memory and web UI guides; the knowledge and app-shell architecture pages.
