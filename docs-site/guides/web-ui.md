---
title: Web UI
description: How Coffer's web UI is served and authenticated, what each page in the sidebar does, and the conventions every page shares.
---

# Web UI

Coffer's web UI is where you manage everything in the vault — agents, MCP servers, skills, knowledge, memory, providers, channels — and chat with your agents. This page explains how the UI is served, tours every page in the sidebar, and lists the conventions the pages share. The [desktop app](/guides/desktop-app) hosts the same UI in a native window.

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

The sidebar groups pages by role: **Agents** are the consumers, **Resources** are what they draw on, **System** is Coffer's own tooling.

| Group | Label | Route | What it is for |
| --- | --- | --- | --- |
| Agents | **Agents** | `/agents` | The AI agents installed on this machine that Coffer manages. Each agent's page has **Overview**, **Skills**, **MCP servers**, **Plugins**, **Memory**, **Conversations** and **Config files** tabs. See [Agents](/guides/agents). |
| Agents | **Chat** | `/chat` | Conversations with Claude Code or Codex, including those started from a channel. See [Chat](/guides/chat). |
| Resources | **MCP servers** | `/mcp-servers` | The upstream MCP servers Coffer aggregates behind one endpoint. See [MCP servers](/guides/mcp-servers). |
| Resources | **Skills** | `/skills` | The skill library Coffer delivers to agents. See [Skills](/guides/skills). |
| Resources | **Knowledge** | `/knowledge` | Collections of documents under `~/.coffer/knowledge/`. See [Knowledge](/guides/knowledge). |
| Resources | **Memory** | `/memory` | Memory aggregated from the agents' own stores. See [Memory](/guides/memory). |
| Resources | **Model providers** | `/model-providers` | Vendor endpoints and their keys. See [Model providers](/guides/providers). |
| Resources | **Channels** | `/channels` | Telegram and SeaTalk bots that let you talk to agents from IM. See [Channels](/guides/channels). |
| System | **Activity** | `/activity` | What changed, what was called and what the daemon logged, as three tabs: **Changes**, **MCP calls** and **Daemon**. See [Activity and audit](/guides/activity). |
| System | **Sync** | `/sync` | Converging this vault with a git remote you own, as **Runs**, **Setup** and **Machines** tabs. See [Vault sync](/guides/vault-sync). |
| System | **Settings** | `/settings` | Preferences, Coffer's own model, retention, encryption and version. |

**Knowledge**, **Memory** and **Sync** are experimental features. When one is switched off, its sidebar entry disappears, and following a link to its page shows a notice with **Open Settings → General** instead. See [Experimental features](/guides/experimental-features).

A red dot beside an entry means something there **Needs your attention** — for example a sync round waiting for you.

Collapse the sidebar to an icon rail with **Collapse sidebar**; the choice is remembered across sessions.

## Settings

Settings has five tabs, in this order. Every field saves as you change it; there is no Save button.

| Tab | Route | What it holds |
| --- | --- | --- |
| **General** | `/settings/general` | **Preferences**: **Theme**, **Default rows per page** and **Preferred editor** (the app Coffer opens managed files with). **Coffer's daemon**: **Start at login** (macOS). **Experimental features**: switch Sync, Knowledge and Memory on or off for this machine. |
| **Coffer's model** | `/settings/engine` | The model provider and model Coffer uses for its own passes, **Speech to text** for voice messages, and **Automatic upkeep** — the passes Coffer runs by itself and how often. |
| **Data** | `/settings/data` | **Data retention** per table — **Keep forever** or a number of days — and **Clear expired data now**. |
| **Security** | `/settings/security` | **Credential encryption**: whether the master key lives in a file beside the database or in the OS keychain. |
| **About** | `/settings/about` | Version, license and source, and **Copy diagnostics**. |

The theme, page size and preferred editor are stored in your browser and never sent to the daemon, except as the target when you open a file. Stopping the daemon and rotating its token are CLI-only (`coffer daemon stop`, `coffer daemon rotate-token`): stopping the daemon from the page would take the page down with it.

## Light and dark

The UI follows your system's light or dark appearance, and switches with it as it changes. To pick one yourself, set **Settings → General → Theme** to **Light** or **Dark**; **System** goes back to following the system. The choice applies at once and is kept in `localStorage` under `coffer.theme`, so each browser and the desktop app keep their own. See [Design system](/architecture/design-system) for how the two themes are built.

## Language

Switch between **English** and **中文** with the language switcher at the bottom of the sidebar. Every label changes immediately, with no reload, and the choice is kept in `localStorage` under `coffer.language`. The switcher is the only language control; the About tab has none.

## Conventions every page shares

**URLs describe what you are looking at.** Every detail page is addressed by the resource's immutable uid — `/mcp-servers/<uid>`, `/skills/<uid>`, `/channels/<uid>` — so renaming a resource does not break a link to it. A page's tab is in the URL too, as `?tab=`: `/agents/<uid>?tab=conversations`, `/activity?tab=mcp`, `/sync?tab=setup`. The default tab leaves the parameter out. A refresh, a bookmark or a shared link reopens the same view. An open conversation is `/chat/<id>`.

**Lists look and behave alike.** Every list page uses one table with search, filters, pagination and bulk selection, and clicking a row opens its detail page. Every row action is labelled.

**Reach is one control.** Resources that agents consume carry a **Reach** button on their row and their detail page: **Every agent**, **Only selected agents**, or none selected (dormant). The choice is written once, when the panel closes, and applies to this machine only. Select several rows to set reach for all of them at once. For a channel, reach means the agents it may drive; see [Channels](/guides/channels#default-agent-and-scope). Knowledge collections and memory partitions carry no reach or status control at all: each is always served to every agent.

**Empty, loading and error states are explicit.** An empty list shows a welcome card with one next step, such as **Add MCP server**. A loading list keeps its header over skeleton rows. A failed request shows a readable message, never a generic error code.

**Some paths redirect.** `/resources` opens **MCP servers**; `/audit` and `/observability` open **Activity**; `/knowledge-bases` opens **Knowledge**; `/settings/providers` opens **Model providers**. Any other unknown path shows a page-not-found view with the sidebar intact.

File trees and previews — on the skill, knowledge, memory and agent pages — fill the window to the bottom and scroll inside. Inside a file viewer, **Cmd+F** (**Ctrl+F**) searches the file.

## When the daemon is not reachable

If a request cannot reach the daemon while the UI is open, a banner floats at the top of the window and the sidebar stays usable:

| Banner | When |
| --- | --- |
| **Daemon not running** | The UI has no working connection to a daemon yet — for example the desktop app is still starting one. It usually clears on its own. |
| **Daemon offline** | A daemon that was answering stopped responding. |
| **Daemon out of date** | The desktop app attached to a daemon left running by an earlier version. Desktop app only. |

The recovery the banner offers depends on the host. In a browser it shows the command to run, `coffer daemon start`, because a page cannot start a daemon. In the desktop app it shows **Restart daemon**. Either way the banner clears itself when the daemon answers again, with no reload.

## Related

- [Desktop app](/guides/desktop-app) — the same UI in a native macOS window.
- [Running the daemon](/guides/daemon) — ports, login service and lifecycle.
- [Security model](/architecture/security) — why the token lives in the page and what the host check protects.
- [Spec: web-ui](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/web-ui/spec.md)
- [A Per-Start Token, Handed to the Page by Whoever Hosts It, Behind a Loopback Host Guard](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/daemon-auth-and-origin-guard.md)
