---
title: Web UI
description: How Coffer's web UI is served and authenticated, how the sidebar, command palette and Settings window are laid out, and the conventions every page shares.
---

# Web UI

Coffer's web UI is where you manage everything in the vault — agents, MCP servers, skills, knowledge, memory, providers, channels — and hold conversations with your agents. This page explains how the UI is served, tours the sidebar, the command palette and the Settings window, and lists the conventions the pages share. The [desktop app](/guides/desktop-app) hosts the same UI in a native window.

## Open the UI

```sh
coffer open
```

```text
opened http://127.0.0.1:8000/ in your browser
```

`coffer open` starts a daemon if none is running, reads the daemon's port from `~/.coffer/daemon.json`, and opens your browser at that address. It passes no credential: the page is authenticated by being served.

| Option | Effect |
| --- | --- |
| `--no-browser` | Print the URL instead of launching a browser. |
| `--json` | Print `{"url": …, "port": …}`. |

The daemon listens on port 8000 by default, so `http://127.0.0.1:8000/` is stable enough to bookmark. If something else needs 8000, move Coffer with `coffer config set daemon.port <port>`; see [Running the daemon](/guides/daemon).

## How the UI is served

The daemon serves the built frontend itself, at its own loopback origin, so the page and the API are the same origin. There is no separate web server and no login screen.

- **The token is in the page.** Every time the daemon serves `index.html` — for `/` and for every client-side route such as `/agents` — it writes its live API token into the document as `window.__COFFER_TOKEN__`. Any page the daemon serves can call the API; nothing is stored in the browser.
- **The page is never cached.** `index.html` is served with `Cache-Control: no-store`, so a restarted daemon's new token always reaches the page. Hashed files under `/assets` are cached normally.
- **Only the daemon's own address and pages are answered.** The daemon refuses a request whose `Host` is not `127.0.0.1`, `localhost` or `[::1]` on its port (`403 HOST_NOT_ALLOWED`). That stops a hostile web page from using DNS rebinding to read the token. It also refuses a request sent from a page on any other origin (`403 ORIGIN_NOT_ALLOWED`). The daemon's own origin and the desktop app are always allowed. To use a dev server, start the daemon with `COFFER_DEV_CORS=1` for Vite on port 5173, or list the origin in `COFFER_CORS_ORIGINS`. See [Security model](/architecture/security#allowing-a-development-origin).

::: warning
Anyone who can load the page from your machine's loopback address can use the vault. Coffer is a single-user local app: do not forward the daemon's port to other machines.
:::

The desktop app cannot receive the token this way, because it loads the UI from its own bundle rather than from the daemon. It hands the page the same two values over IPC; see [Desktop app](/guides/desktop-app#how-it-connects).

## The sidebar

The sidebar is grouped by what you come to Coffer to do. **Overview** sits on top under no heading, because it summarises everything below it; then five groups follow.

| Group | Entry | Route | What it is for |
| --- | --- | --- | --- |
| — | **Overview** | `/` | The landing page: what needs you, the health of every area and the last few changes. See [Overview](#overview) below. |
| Agents | **Agents** | `/agents` | The AI agents installed on this machine that Coffer manages. Each agent's page has **Overview**, **Skills**, **MCP servers**, **Plugins**, **Memory**, **Conversations** and **Config files** tabs. See [Agents](/guides/agents). |
| Agents | **Model providers** | `/model-providers` | Vendor endpoints and their keys — the models your agents run on. See [Model providers](/guides/providers). |
| Run | **Conversations** | `/conversations` | Conversations with Claude Code or Codex, including those started from a channel. See [Chat](/guides/chat). |
| Run | **Channels** | `/channels` | Telegram and SeaTalk bots that let you talk to agents from IM. See [Channels](/guides/channels). |
| Capabilities | **MCP servers** | `/mcp-servers` | The upstream MCP servers Coffer aggregates behind one endpoint. See [MCP servers](/guides/mcp-servers). |
| Capabilities | **Custom tools** | `/custom-tools` | Tools you define yourself for your agents. |
| Capabilities | **Skills** | `/skills` | The skill library Coffer delivers to agents. See [Skills](/guides/skills). |
| Capabilities | **CLIs** | `/clis` | The command-line tools your skills need, and whether each is installed. |
| Context | **Knowledge** | `/knowledge` | Collections of documents under `~/.coffer/knowledge/`. See [Knowledge](/guides/knowledge). |
| Context | **Memory** | `/memory` | Memory aggregated from the agents' own stores. See [Memory](/guides/memory). |
| System | **Secrets** | `/secrets` | Every stored secret with what uses it: add, replace, delete, find plaintext keys in files and move them into the vault. See [Secrets](/guides/secrets). |
| System | **Activity** | `/activity` | What changed, what agents called and what the daemon logged: **Everything** merged into one stream, then **Changes**, **MCP calls** and **Daemon log**. See [Activity and audit](/guides/activity). |
| System | **Usage** | `/usage` | Each subscription's quota as its agent reported it, and the tokens and estimated cost of API-key requests through Coffer's local proxy. See [Usage](/guides/usage). |
| System | **Sync** | `/sync` | Converging this vault with a git remote you own, as **Runs**, **Setup** and **Machines** tabs. See [Vault sync](/guides/vault-sync). |

In Chinese the groups read 智能体 · 运行 · 能力 · 上下文 · 系统, and an agent is always called 智能体.

::: info Pages still being built
**Custom tools** and **CLIs** have their place in the sidebar already, but for now each shows a "Coming in this release" notice: their pages arrive later in this release. Every other entry works today.
:::

**Knowledge**, **Memory** and **Sync** are experimental features. While one is switched off its entry is left out of the sidebar, and a group whose entries are all switched off loses its heading too. While one is on, its entry carries an **Experimental** marker. Following a link to a switched-off feature's page shows a notice saying the feature is off. Features are switched on and off from the command line, `coffer config set feature.<key> on`; see [Experimental features](/guides/experimental-features).

**Attention dots.** A small dot beside an entry means something there **Needs your attention** — today, a sync round that is held or failed and waiting for you. It is a dot, not a count, and it clears once you visit the page. The dot stays visible on the collapsed rail.

**Collapsing and resizing.** Collapse the sidebar to a narrow icon rail with **Collapse sidebar**; the choice is remembered. While expanded, drag the thin line on its right edge to make it wider or narrower (see [Resizing split views](#resizing-split-views)).


## Overview

**Overview** is the page the app opens on. It answers "is everything OK, and what needs me?" in three parts:

- **Needs you** — one row per problem across every area, most severe first and then oldest: the thing it is about (a server, an agent, a channel, the vault's sync), the reason in a sentence, since when, and one button that opens the page where you deal with it. The list is the daemon's attention list (`GET /api/v1/attention`, or `coffer attention` in a terminal). Rows clear themselves: the page follows the daemon's event stream, so a row disappears as soon as its problem is resolved. If one area could not be checked, the page says so above the rows, because anything that area would report is missing. When nothing needs you, a calm card says so.
- **Health** — a tile per area: Agents, Model providers, MCP servers, Skills and Channels, plus Knowledge, Memory and Sync when those features are switched on. Each shows a status word, a count and a one-line summary (for MCP servers, the calls and errors of the last 24 hours) and opens the area's page. A tile that fails to load says so with **Retry**, and the rest of the page keeps working. Areas that have no backend yet, such as Custom tools and CLIs, have no tile.
- **Recent activity** — the last few changes, with a link to [Activity](/guides/activity).

Before any agent is registered, Overview opens on connecting one instead: it lists the agents Coffer supports and which it found on this machine, then the first step for each thing they share.

## Search or jump to

The **Search or jump to…** control at the top of the sidebar opens the command palette; so does **⌘K** (**Ctrl+K**) from anywhere. Type a few letters, move with the arrow keys, press **Enter** to go there, **Escape** to close and return to where you were.

The palette is for navigation only — it takes you somewhere and never runs an action. It lists two groups:

- **Pages** — every sidebar entry and every Settings tab. Pages are always available, even while the daemon is offline.
- **Objects** — your agents, MCP servers, skills, model providers, channels, knowledge collections and memory partitions, matched by name (and by title on the kinds that carry one). Each kind loads on its own: while one loads its group says so, and if one fails only that group shows an error. While the daemon cannot be reached, the palette lists Pages only and says that objects need the daemon.

Pages and objects of a switched-off experimental feature are left out.

## The sidebar footer

The bottom of the sidebar holds three things, top to bottom.

- **Settings** — a labelled row with a gear. It opens the Settings window (below) and is highlighted while that window is open. On the collapsed rail it is the gear alone, with a tooltip.
- **The daemon's state, in plain words** — **Connecting to the daemon…**, **Daemon running on port 8000**, **Daemon stopping** or **Daemon offline**. It always agrees with the offline banner: while the banner is up, the footer never reads as running. Click it to open **Settings → Daemon**.
- **The language switcher.**

## Settings

Settings opens as a large window over the page you are on, so closing it puts you back exactly where you were. Open it with the **Settings** row, with **⌘,** (**Ctrl+,**) when you are not typing in a field, or from the palette. Every field saves as you change it; there is no Save button.

It has five tabs, in this order:

| Tab | Address | What it holds |
| --- | --- | --- |
| **General** | `/settings/general` | Display preferences — **Theme**, **Default rows per page**, **Preferred editor** (the app Coffer opens managed files with) — and **Coffer's model**: a provider and model for **Coffer's engine** and for **Speech to text**, each with **Test** and an inline not set / answering / failing state, and **Automatic upkeep**, the passes Coffer runs by itself and how often. |
| **Security** | `/settings/security` | Only what belongs to this Mac. **Encryption**: where the master key lives (a signed release keeps it in its Keychain, with nothing to move) and **Back up the master key** (desktop app only). **Access**: the daemon's access token, hidden until **Show**, with **Copy** and **Rotate…**. **Approvals**: whether a secret waits for your approval before it goes somewhere new, and **Review** for what waits. Stored secrets are on the [Secrets](/guides/secrets) page, not here. |
| **Data** | `/settings/data` | **Data retention** per table — **Keep forever** or a number of days — and **Clear expired data now**. |
| **Daemon** | `/settings/daemon` | The daemon's state, port, version and when it started, and **Start at login** (macOS). |
| **About** | `/settings/about` | Version, license and source, and **Copy diagnostics**. In the desktop app, **Updates**: when Coffer last checked, **Check for updates**, a newer version with **Download and restart**, and **Check automatically** (see [Desktop app → Update](/guides/desktop-app#update)). In a browser it says updates are installed by the desktop app. |

**Each tab has its own address.** Opening a tab changes the URL to `/settings/<tab>`, so a bookmark or a shared link opens that tab directly. Close the window with **×**, **Escape**, a click outside it or the browser's **Back** button: you return to the page underneath, at its own address. If you load a `/settings/<tab>` address fresh, it opens over **Overview**, and closing it lands on `/`.

**Old addresses still work.** `/settings/engine` and `/settings/embedding` open **General**; `/settings/llm-connections`, `/settings/models` and `/settings/providers` open **Model providers**; `/settings/sync` opens **Sync**.

The theme, page size and preferred editor are stored in your browser and never sent to the daemon, except as the target when you open a file. Stopping the daemon is CLI-only (`coffer daemon stop`): stopping it from the page would take the page down with it. Rotating the access token is on **Settings › Security** (or `coffer daemon rotate-token`); the page installs the new token and keeps working, and other open tabs and clients using the old one stop until they load the new one. Revealing or copying a secret, backing up the master key and approving a pending [approval](/guides/secrets#approvals) exist only in the [desktop app](/guides/desktop-app#presence-checks-and-approvals), because each needs a Touch ID or password check a browser cannot run; a browser tab shows **Open in Coffer app** in their place.

## Resizing split views

Wherever the window is split side by side — the sidebar against the page, and the conversation list against the open conversation — the two halves are divided by a thin line you can drag. The line lights up in the accent colour while you hover over or drag it.

- **Drag** it to resize. **Double-click** it to go back to the default width.
- **From the keyboard**, tab to the line and press **←** or **→** to move it in small steps.
- **Limits keep both sides usable.** The sidebar stays between 200 and 300 pixels wide (220 by default). A list is at least 240 pixels and at most half the split, and the detail beside it keeps at least 480.
- **Widths are remembered per page, in this browser.** It is a convenience only: another browser, the desktop app or a private window starts from the defaults, and nothing is sent to the daemon.

## Light and dark

The UI follows your system's light or dark appearance, and switches with it as it changes. To pick one yourself, set **Settings → General → Theme** to **Light** or **Dark**; **System** goes back to following the system. The choice applies at once and is kept in `localStorage` under `coffer.theme`, so each browser and the desktop app keep their own. See [Design system](/architecture/design-system) for how the two themes are built.

## Language

Switch between **English** and **中文** with the language switcher at the bottom of the sidebar. Every label changes immediately, with no reload, and the choice is kept in `localStorage` under `coffer.language`. The switcher is the only language control; the About tab has none.

## Conventions every page shares

**URLs describe what you are looking at.** A refresh, a bookmark or a shared link reopens the same view. A detail page's tab is part of its path: the default tab is the bare address, any other tab adds its name — `/mcp-servers/github` and `/mcp-servers/github/tools`. Skills and MCP servers are addressed by their name, which is fixed once registered (`/skills/release-notes`), and an agent by its type, since there is one per type (`/agents/claude_code/skills`). Kinds you can rename — model providers, channels, knowledge collections, memory partitions — are addressed by their immutable uid (`/model-providers/<uid>/models`), so a rename does not break a link. Activity and Sync still carry their tab as `?tab=` (`/activity?tab=mcp` — Everything is the bare `/activity` — `/sync?tab=setup`) until they are rebuilt, and an open file in a tree is `?file=`. An open conversation is `/conversations/<id>`.

**Lists look and behave alike.** Every list page uses one table with search, filters, pagination and bulk selection, and clicking a row opens its detail page. Every row action is labelled.

**Reach is one control.** Resources that agents consume carry a **Reach** button on their row and their detail page: **Every agent**, **Only selected agents**, or none selected (dormant). The choice is written once, when the panel closes, and applies to this machine only. Select several rows to set reach for all of them at once. For a channel, reach means the agents it may drive; see [Channels](/guides/channels#default-agent-and-scope). Knowledge collections and memory partitions carry no reach or status control at all: each is always served to every agent.

**Empty, loading and error states are explicit.** An empty list shows a welcome card with one next step, such as **Add MCP server**. A loading list keeps its header over skeleton rows. A failed request shows a readable message, never a generic error code.

**Some paths redirect.** `/chat` opens **Conversations**; `/resources` opens **MCP servers**; `/audit` and `/observability` open **Activity**; `/knowledge-bases` opens **Knowledge**. Old `?tab=` links to a skill, MCP server or model provider, and old uid links to a skill or MCP server, move to the current address. Any other unknown path shows a page-not-found view with the sidebar intact.

File trees and previews — on the skill, knowledge, memory and agent pages — fill the window to the bottom and scroll inside. Inside a file viewer, **Cmd+F** (**Ctrl+F**) searches the file.

## When the daemon is not reachable

If a request cannot reach the daemon while the UI is open, a banner floats at the top of the window, the sidebar footer reads **Daemon offline**, and the sidebar stays usable:

| Banner | When |
| --- | --- |
| **Daemon not running** | The UI has no working connection to a daemon yet — for example the desktop app is still starting one. It usually clears on its own. |
| **Daemon offline** | A daemon that was answering stopped responding. |
| **Daemon out of date** | The desktop app attached to a daemon left running by an earlier version. Desktop app only. |

The recovery the banner offers depends on the host. In a browser it shows the command to run, `coffer daemon start`, because a page cannot start a daemon. In the desktop app it shows **Restart daemon**. Either way the banner clears itself when the daemon answers again, with no reload.

## Related

- [Desktop app](/guides/desktop-app) — the same UI in a native macOS window.
- [Running the daemon](/guides/daemon) — ports, login service and lifecycle.
- [App shell](/architecture/app-shell) — why the sidebar is grouped the way it is, and how Settings, the palette and the footer are built.
- [Security model](/architecture/security) — why the token lives in the page and what the host check protects.
- [Spec: web-ui](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/web-ui/spec.md)
- [A Per-Start Token, Handed to the Page by Whoever Hosts It, Behind a Loopback Host Guard](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/daemon-auth-and-origin-guard.md)
