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
| Run | **Conversations** | `/conversations` | Every conversation Coffer runs — started here or from a channel — with its source, filters by source and agent, and a reply box to continue any of them. See [Conversations](/guides/chat). |
| Run | **Channels** | `/channels` | Telegram and SeaTalk bots that let you talk to agents from IM: setup, connection status and settings; each links to its conversations. See [Channels](/guides/channels). |
| Capabilities | **MCP servers** | `/mcp-servers` | The upstream MCP servers Coffer aggregates behind one endpoint. See [MCP servers](/guides/mcp-servers). |
| Capabilities | **Custom tools** | `/custom-tools` | HTTP API requests your agents call as tools — see [Custom tools](/guides/custom-tools). |
| Capabilities | **Skills** | `/skills` | The skill library Coffer delivers to agents. See [Skills](/guides/skills). |
| Capabilities | **CLIs** | `/clis` | The command-line tools your skills need, and whether each is installed — see [CLIs](/guides/clis). |
| Context | **Knowledge** | `/knowledge` | Collections of documents under `~/.coffer/knowledge/`: one tree beside a reader and editor, each collection's Inbox, every document's History and Recent changes. See [Knowledge](/guides/knowledge). |
| Context | **Memory** | `/memory` | What your agents learned, read from their own memory and distilled into one memory per subject: deliveries at session start over the last 7 days, and the partitions. A partition's page has **Memories** and **Delivered** tabs. See [Memory](/guides/memory). |
| System | **Secrets** | `/secrets` | Every stored secret with what uses it: add, replace, delete, find plaintext keys in files and move them into the vault. See [Secrets](/guides/secrets). |
| System | **Activity** | `/activity` | What changed, what agents called and what the daemon logged: **Everything** merged into one stream, then **Changes**, **MCP calls** and **Daemon log**. See [Activity and audit](/guides/activity). |
| System | **Usage** | `/usage` | Each subscription's quota as its agent reported it, and the tokens and estimated cost of API-key requests through Coffer's local proxy. See [Usage](/guides/usage). |
| System | **Sync** | `/sync` | Converging this vault with a git remote you own, as **Runs**, **Setup** and **Machines** tabs. See [Vault sync](/guides/vault-sync). |

In Chinese the groups read 智能体 · 运行 · 能力 · 上下文 · 系统, and an agent is always called 智能体.

::: info Pages still being built
:::

An entry that belongs to an [experimental feature](/guides/experimental-features) carries an **Experimental** label while the feature is on. While it is switched off the entry is left out of the sidebar, a group whose entries are all switched off loses its heading too, and following a link to its page shows a notice saying the feature is off. No feature is experimental right now, so no entry carries the label.

**Attention badges.** A number beside an entry counts the things there that **Need your attention**: MCP servers, agents, skills and channels that are failing or have drifted from what Coffer wrote (the same items as Overview's **Needs you**), a sync round that is held or failed (cleared once you visit Sync), and required CLIs that are missing, too old or not logged in. The badge is red while any of them is a failure. Informational counts never become badges — documents waiting in a knowledge collection's inbox show only as the **Inbox** count in its tree. On the collapsed rail a badge shrinks to a dot of the same colour, and the icon's tooltip carries the count (**MCP servers · 1 failing**).

**Collapsing and resizing.** Collapse the sidebar to a 56-pixel icon rail with **Collapse sidebar** beside the Coffer mark; the rail's **Expand sidebar** button sits in its footer, between the gear and the daemon's dot, and the choice is remembered. While expanded, drag the thin line on its right edge to make it wider or narrower (see [Resizing split views](#resizing-split-views)).


## Overview

**Overview** is the page the app opens on. It answers "is everything OK, and what needs me?" in three parts:

- **Needs you**: one row per problem across every area, most severe first and then oldest. Each row names the thing it is about (a server, an agent, a channel, the vault's sync), gives the reason in a sentence and since when, and has one button that opens the page, or the tab, where you deal with it. A memory hook that was changed by hand in an agent's settings and that Coffer could not rewrite opens that agent's **Hooks** tab with **Repair hook**. The list is the daemon's attention list (`GET /api/v1/attention`, or `coffer attention` in a terminal). Rows clear themselves: the page follows the daemon's event stream, so a row disappears as soon as its problem is resolved. If one area could not be checked, the page says so above the rows, because anything that area would report is missing. An agent that is simply not connected also has a **⋯** menu with **Ignore**. Ignored items leave the list and are counted under it (**1 ignored · Show**), and **Show** lists them again with **Stop ignoring**. Ignoring is remembered by Coffer on this Mac (not synced to your other machines) and changes nothing about the agent. An ignored item also leaves the sidebar's badges and the menu bar's count. Only something worth knowing but not broken can be ignored. When nothing needs you, a calm card says so, with when it last checked.
- **Health**: a tile per area: Agents, MCP servers, Skills, Knowledge, Memory, Model providers, Channels, Sync, Custom tools, CLIs, Secrets and Usage. Each shows a status word, a count and a one-line summary (for MCP servers, the calls and errors of the last 24 hours; for Usage, today's tokens, cost and each provider's share) and opens the area's page. A tile that fails to load says so with **Retry** and a link to its page, and the rest of the page keeps working.
- **Recent activity**: the last few changes, with a link to [Activity](/guides/activity).

Before any agent is registered, Overview opens on connecting one instead. It lists the agents Coffer supports, each with its config folder and whether it was found on this machine. The found ones are ticked, and **Review and connect** shows every file change before Coffer writes anything. If none was found, it says so and offers **Scan again**, and **Copy prompt** copies a prompt Coffer writes for your assistant to install one of them on this Mac; Coffer names no installer itself. **Add an agent by hand** opens the Agents page, and below comes the first step for each thing agents share.

## Search or jump to

The **Search or jump to…** control at the top of the sidebar opens the command palette; so does **⌘K** (**Ctrl+K**) from anywhere. Type a few letters, move with the arrow keys, press **Enter** to go there, **Escape** to close and return to where you were.

The palette is for navigation only — it takes you to pages and objects and never runs an action; actions stay on their page. It finds:

- **Pages** — every sidebar entry and every Settings tab. Pages are always available, even while the daemon is offline.
- **Objects** — your agents, model providers, conversations, channels, MCP servers, custom tools, skills, CLIs, knowledge collections, memory partitions and secrets, matched by name (and by title on the kinds that carry one), each with a status word where its list has one (**Failing**, **Off**, **Missing**). Each kind loads on its own: while they load the palette says so, and if one fails only that kind shows an error. While the daemon cannot be reached, the palette lists Pages only and says that objects need the daemon.

With nothing typed it shows **Recent** — the last few things you opened from it, remembered in this browser — above every page. Once you type, the single best hit leads as **Best match** (an exact name first), then the other matching pages, then the matching objects grouped by kind in sidebar order. A query that matches nothing says so.

Pages and objects of a switched-off [experimental feature](/guides/experimental-features) are left out.

## The sidebar footer

The bottom of the sidebar holds, top to bottom:

- **Update ready** — in the desktop app, when a newer version has been found: a card naming it with **Restart** (downloads it, checks its signature, installs it and reopens Coffer) and **What's new** (Settings › About). Dismiss it and it comes back at the next launch; it is never a popup.
- **Settings** — a labelled row with a gear. It opens the Settings window (below) and is highlighted while that window is open. On the collapsed rail it is the gear alone, with the tooltip **Settings ⌘,**.
- **The daemon's state and the app's version** — **Connecting to the daemon…**, **Daemon running**, **Daemon stopping**, **Reconnecting…** or **Daemon offline**, with the version on the right. It always agrees with the connection states below: it never reads as running while the daemon is away. On the collapsed rail it is a coloured dot whose tooltip says the same.

Click the daemon's state to open the **version menu**. Its first line names the version and the address the daemon answers on (`127.0.0.1:8000`) and opens **Settings → Daemon**. Below it:

- **Theme** — **Light**, **Dark** or **System**, applied at once.
- **Language** — **English** or **简体中文**, each named in its own language, applied at once.
- **Documentation** — this site.
- **Check for updates** — opens **Settings › About**; in the desktop app it checks right away.

## Settings

Settings opens as a large window over the page you are on, so closing it puts you back exactly where you were. Open it with the **Settings** row, with **⌘,** (**Ctrl+,**) when you are not typing in a field, or from the palette. Every field saves as you change it; there is no Save button.

It has five tabs, in this order:

| Tab | Address | What it holds |
| --- | --- | --- |
| **General** | `/settings/general` | **Appearance** — **Language** and **Theme** (Light, Dark or System) — **Tables and files** — **Rows per page** (how many rows a list shows before **Load N more**) and **Open files with** (the app Coffer opens managed files with) — and **Coffer's model**: a provider and model for **Coffer's engine** and for **Speech to text**, each with **Test** and an inline not set / answering / failing state. The passes Coffer runs by itself are switched from the **Automatic** control on the Knowledge and Memory pages. |
| **Security** | `/settings/security` | Only what belongs to this Mac. **Encryption**: where the master key lives (a signed release keeps it in its Keychain, with nothing to move) and **Back up the master key** (desktop app only). **Access**: the daemon's access token, hidden until **Show**, with **Copy** and **Rotate…**. **Approvals**: whether a secret waits for your approval before it goes somewhere new, and **Review** for what waits. Stored secrets are on the [Secrets](/guides/secrets) page, not here. |
| **Data** | `/settings/data` | What Coffer keeps, by kind. **Vault** — the synced git repository of your configuration, skills and knowledge: its size, how many versions it holds, **Open folder** (before Sync is set up, the trees it would carry). **Local content** — chat and channel attachments, which are not synced: back that folder up yourself. **History** — how long **Changes**, **MCP calls** and **Conversations** are kept (**Keep forever** or a number of days; shortening asks first and says how many records the next cleanup deletes), cleaned up every six hours, with **Clear expired data now**. **Rebuildable cache** — the memory tree and the transcript summary cache: **Clear** asks first, and memory is rebuilt from the agents' own memory on the next update. |
| **Daemon** | `/settings/daemon` | The daemon's status — its state and address, how long it has been up, its pid and how many agents are connected to Coffer — with **Restart** in the desktop app, or the `coffer daemon restart` command to copy in a browser. **Startup**: **Start at login** (macOS) and **Port** (1024–65535, default 8000; a port another program holds, or one outside the range, is refused in place and Save stays off until you change it). A saved port reads **takes effect after Coffer restarts**, with **Restart now** in the app; agents reconnect to it on their own. While the daemon is offline the tab names how to bring it back and the controls are disabled. There is no token here (it is on Security) and no stop control. |
| **About** | `/settings/about` | The version with **Copy diagnostics for a bug report** beside it (version, channel, host, daemon state and port, enabled features — never a token or a secret); **Details**: the version with the commit a release was built from, license, source and the data folder. In the desktop app, **Updates**: when Coffer last checked, **Check for updates**, a newer version with **Download and restart**, and **Check automatically** (see [Desktop app → Update](/guides/desktop-app#update)). In a browser it says updates are installed by the desktop app. |

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

The UI follows your system's light or dark appearance, and switches with it as it changes. To pick one yourself, choose **Light** or **Dark** in the version menu (click the daemon's state at the foot of the sidebar) or in **Settings → General → Theme**; **System** goes back to following the system. The choice applies at once and is kept in `localStorage` under `coffer.theme`, so each browser and the desktop app keep their own. See [Design system](/architecture/design-system) for how the two themes are built.

## Language

Switch between **English** and **简体中文** in the version menu at the foot of the sidebar, or in **Settings → General → Language**. Every label changes immediately, with no reload, and the choice is kept in `localStorage` under `coffer.language`. The About tab has no language control.

## Conventions every page shares

**URLs describe what you are looking at.** A refresh, a bookmark or a shared link reopens the same view. A detail page's tab is part of its path: the default tab is the bare address, any other tab adds its name — `/mcp-servers/github` and `/mcp-servers/github/tools`. Skills and MCP servers are addressed by their name, which is fixed once registered (`/skills/release-notes`), and an agent by its type, since there is one per type (`/agents/claude_code/skills`). Kinds you can rename — model providers, channels, knowledge collections, memory partitions — are addressed by their immutable uid (`/model-providers/<uid>/models`), so a rename does not break a link. Activity and Sync still carry their tab as `?tab=` (`/activity?tab=mcp` — Everything is the bare `/activity` — `/sync?tab=setup`) until they are rebuilt, and an open file in a tree is `?file=`. An open conversation is `/conversations/<id>` and the draft **New conversation** opens is `/conversations/new`; the list's filters are search parameters (`/conversations?source=seatalk&agent=codex`, `?channel=<uid>`).

**Lists look and behave alike.** Every list page uses one table with search, filters, pagination and bulk selection, and clicking a row opens its detail page. Every row action is labelled.

**Reach is one control.** Resources that agents consume carry a **Reach** button on their detail page and, in a table, on their row (the MCP servers and Skills lists read each row's reach and put the button on the open item): **Every agent**, **Only selected agents**, or none selected (dormant). The choice is written once, when the panel closes, and applies to this machine only. Select several rows to set reach for all of them at once. For a channel, reach means the agents it may drive; see [Channels](/guides/channels#default-agent-and-scope). Knowledge collections and memory partitions carry no reach or status control at all: each is always served to every agent.

**Empty, loading and error states are explicit.** An empty list shows a welcome card with one next step, such as **Add server**. A loading list keeps its header over skeleton rows. A failed request shows a readable message, never a generic error code.

**Some paths redirect.** `/chat` opens **Conversations**; `/resources` opens **MCP servers**; `/audit` and `/observability` open **Activity**; `/knowledge-bases` opens **Knowledge**. Old `?tab=` links to a skill, MCP server or model provider, and old uid links to a skill or MCP server, move to the current address. Any other unknown path shows a not-found page with the sidebar intact: it names the address, suggests the closest page when one is close (**Did you mean /mcp-servers**), and offers **Back to Overview** and **Search Coffer** (the palette).

File trees and previews — on the skill, knowledge and agent pages, and a memory partition's list — fill the window to the bottom and scroll inside. Inside a file viewer, **Cmd+F** (**Ctrl+F**) searches the file.

## When the daemon is not reachable

The UI checks the daemon every 30 seconds. When it stops answering, the UI retries after 1, 2, 4 and 8 seconds and shows what is happening at the top of the workspace, while the sidebar stays usable:

| State | When | What you see |
| --- | --- | --- |
| **Reconnecting to the daemon…** | The first 10 seconds after it stopped answering (**Connecting to the daemon…** if it never answered). | The page stays where it was, dimmed and paused, under a bar that counts the attempts and says nothing is lost, with **Retry now**. The footer reads **Reconnecting…**. |
| **Coffer's daemon isn't running** | After that. | The page makes way for a screen naming the address the UI talks to, when it checks next and when the daemon last answered, with **Retry**. The footer reads **Daemon offline**. |
| **Daemon out of date** | The desktop app attached to a daemon left running by an earlier version. Desktop app only. | A bar over the page with **Restart daemon**. |

The recovery the offline screen offers depends on the host. In a browser it shows the command to run, `coffer daemon start`, because a page cannot start a daemon. In the desktop app it shows **Start daemon**. Either way the screen clears itself when the daemon answers again, with no reload: every list is read again and a **Reconnected** notice appears.

## Related

- [Desktop app](/guides/desktop-app) — the same UI in a native macOS window.
- [Running the daemon](/guides/daemon) — ports, login service and lifecycle.
- [App shell](/architecture/app-shell) — why the sidebar is grouped the way it is, and how Settings, the palette and the footer are built.
- [Security model](/architecture/security) — why the token lives in the page and what the host check protects.
- [Spec: web-ui](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/web-ui/spec.md)
- [A Per-Start Token, Handed to the Page by Whoever Hosts It, Behind a Loopback Host Guard](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/daemon-auth-and-origin-guard.md)
