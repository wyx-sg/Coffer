## MODIFIED Requirements

### Requirement: Switch language from the sidebar
The sidebar MUST offer the English / 简体中文 switch from every screen: in the
version menu its footer opens (see "Show the daemon's state in the shell
footer"), each locale named in its own language, and in Settings › General.
Every sidebar label, page title and form label MUST switch on the very next
render, with no full page reload, and the choice MUST persist in `localStorage`
under `coffer.language`.

#### Scenario: language switcher round-trips correctly
- **GIVEN** the UI is in English
- **WHEN** the user opens the version menu from the sidebar footer and selects 简体中文
- **THEN** all sidebar labels, page titles, and form labels switch to Chinese without a full page reload, on the very next render
- **AND** the preference persists across reloads (localStorage `coffer.language`)

## ADDED Requirements

### Requirement: Offer a found update in a card above the sidebar footer
In the desktop shell, when the shell's update check has found a newer version,
a card MUST sit above the sidebar's Settings row naming the version, with
**Restart** — which asks the shell to download, verify and install it and then
relaunch, the same install as Settings › About's (spec web-ui "Check for and
install updates on Settings › About") — and **What's new**, opening Settings ›
About with the release notes. The card is never a modal. It MUST be dismissible,
and a dismissed card MUST come back at the next launch. While the install runs
Restart MUST show that it is busy, and an install the shell refuses MUST leave
the card up with the reason. The collapsed icon rail shows no card, and a
browser shows none, because a page the daemon serves cannot replace the
application.

#### Scenario: a found update shows a dismissible card in the desktop shell only
- **GIVEN** the shell's update check reporting version 1.1.0 available
- **WHEN** the sidebar renders in the desktop shell, and then in a browser
- **THEN** the desktop sidebar shows a card above the Settings row naming v1.1.0 with Restart and What's new, and Restart asks the shell to install it
- **AND** after the user dismisses it the card is gone, while the browser never shows one

### Requirement: Suggest the closest page for an unknown address
An address no route matches MUST render a not-found page in the workspace,
with the shell around it, that names the address, suggests the sidebar page
closest to its first segment when one is close ("Did you mean /mcp-servers"),
and offers **Back to Overview** and **Search Coffer**, which opens the command
palette over the page.

#### Scenario: an unknown address suggests the closest page
- **GIVEN** the user opens `/mcp/sentri`
- **WHEN** the route resolves
- **THEN** the page says nothing lives at `/mcp/sentri`, suggests `/mcp-servers`, and offers Back to Overview and Search Coffer
- **AND** Search Coffer opens the command palette

### Requirement: Send a memory-hook problem on Overview to the agent's Hooks tab
When Coffer's memory hook in an agent's own settings no longer matches what Coffer installs —
its command or events were changed by hand — and a reconciler pass tried to rewrite it and could
not, Overview's Needs you MUST list it as a row on that agent: the reason in a sentence, since when
the pass first saw it, and one action, **Repair hook**, opening the agent's Hooks tab, where the
hook's row carries Repair. A hand-edited hook that no pass has visited yet MUST NOT be listed: the
next pass rewrites it on its own. The hook's other problems the reconciler reports on the agent —
missing, not trusted or switched off in the agent, a settings file that does not parse — MUST open
the same tab.

#### Scenario: a memory hook changed by hand that coffer could not rewrite needs the user
- **GIVEN** Claude Code connected to Coffer, with the command of Coffer's memory hook changed by hand in its settings
- **WHEN** no reconciler pass has run yet, and then a pass tries to rewrite the hook and fails
- **THEN** before the pass the attention list holds no item for it, and after it the list holds one warning on Claude Code whose reason says the hook no longer matches what Coffer installs, with since set and the repair action for that change

#### Scenario: a memory hook changed by hand opens the agent's hooks tab from overview
- **GIVEN** the attention list holds the hand-edited memory hook of Claude Code
- **WHEN** the user opens Overview
- **THEN** Needs you shows a row on Claude Code with the reason and since when, its one action reads Repair hook and opens Claude Code's Hooks tab, its name opens Claude Code's page, and the row has no menu

### Requirement: Let the user ignore an unconnected agent on Overview
An agent that Overview lists only because it is not connected to Coffer — an informational item of
the attention list — MUST carry a ⋯ menu with **Ignore** beside its Connect action. The daemon MUST
remember an ignored item on this machine, by the item's stable key (its kind, resource and reason),
and audit each ignore and each stop: `GET /api/v1/attention` then lists it under `ignored`, out of
`items` and `counts_by_kind`, so Needs you, the Agents health tile, the sidebar's badges and the
menu bar's count all leave it out alike. Overview MUST count the ignored items under the list as
**N ignored · Show**; Show lists them again, muted, each with **Stop ignoring** in its menu.
Ignoring changes nothing about the agent. Only an informational item can be ignored; asking to
ignore anything else is refused with `ATTENTION_NOT_IGNORABLE`, because something broken stays
until it is fixed.

#### Scenario: an ignored agent leaves needs you and is counted under it
- **GIVEN** Overview listing Codex as not connected and an MCP server that fails
- **WHEN** the user chooses Ignore in Codex's menu, then Show, then Stop ignoring on Codex
- **THEN** Codex leaves the list while the server stays and "1 ignored · Show" appears under it; Show lists Codex again under the list; after Stop ignoring Codex is back in Needs you and nothing is counted as ignored
- **AND** while Codex is ignored the daemon's attention list carries it only under `ignored`, its counts leave it out, both changes are audited, and ignoring the failing server is refused
