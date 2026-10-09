---
title: Web UI
description: How Coffer's web UI is served and authenticated, how the sidebar, command palette and Settings window are laid out, and the conventions every page shares.
---

# Web UI

Coffer's web UI is where you manage everything in the vault — agents, MCP servers, skills, knowledge, memory, providers, channels — and hold conversations with your agents. This page explains how the UI is served, tours the sidebar, the command palette and the Settings window, and lists the conventions the pages share. The [desktop app](/guides/desktop-app) hosts the same UI in a native window.

## What the web UI and the command line each do

Every management operation is in the web UI, and every one also has a `coffer` command that calls the same route, so an agent working in a terminal can do it too: `coffer agent`, `coffer mcp`, `coffer custom-tool`, `coffer skill`, `coffer knowledge`, `coffer memory`, `coffer provider`, `coffer channel`, `coffer approval`, `coffer sync`, `coffer settings` and the rest. Validation, audit and lifecycle are the same whoever acts. [CLI coverage](/reference/cli-coverage) maps each page action to its route and command, and the [CLI reference](/reference/cli) lists every option. Every command takes `--json`, reads a body from `--data '<json>'`, `--data @file` or `--data -` (standard input) with repeatable `--set key=value`, passes the daemon's error codes through, and exits with a stable [exit code](/reference/error-codes#cli-exit-codes).

Two things have no command. Plain file contents — a knowledge document, a memory note, a skill's files, an agent's own config — are read and edited with your or your agent's own tools. Acts that only make sense at a window — a folder picker, opening a file in your editor, terminal or Finder, the interface's language and theme — stay in the window. A step that needs your presence (approving a secret, revealing a value, backing up the master key) is handed to the [desktop app](/guides/desktop-app)'s own Touch ID check, whichever surface starts it.

## Open the UI

Start the daemon (the [desktop app](/guides/desktop-app) does it for you, or `coffer daemon start`), then browse to `http://127.0.0.1:<port>/`, where `<port>` is the port in `~/.coffer/daemon.json`. The page passes no credential: it is authenticated by being served.

The daemon listens on port 38470 by default, so `http://127.0.0.1:38470/` is stable enough to bookmark. If something else needs 38470, move Coffer with `coffer config set daemon.port <port>` (the one setting the CLI changes, because it is read before the page can load); see [Running the daemon](/guides/daemon).

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
| Agents | **Agents** | `/agents` | The AI agents installed on this machine that Coffer manages. Each agent's page has **Overview**, **Skills**, **MCP servers**, **Hooks**, **Config files** and **Sessions** tabs, with **Plugins** and **Memory** behind **More**; its model is changed from the Overview. See [Agents](/guides/agents). |
| Agents | **Model providers** | `/model-providers` | Vendor endpoints and their keys — the models your agents run on — on the **Providers** tab, and what requests through Coffer cost on the **Usage** tab (`?tab=usage`). See [Model providers](/guides/providers) and [Usage](/guides/usage). |
| Run | **Conversations** | `/conversations` | Every agent's sessions, wherever they were started — in a terminal, by a channel or from New conversation — as one list: title, source, agent, directory and last activity, with search, filters by source and agent, and a button on each row that resumes the session in your terminal. See [Conversations](/guides/chat). |
| Run | **Channels** | `/channels` | Telegram and SeaTalk bots that let you talk to agents from IM: setup, connection status and settings; each links to the conversations it started. See [Channels](/guides/channels). |
| Capabilities | **MCP servers** | `/mcp-servers` | The upstream MCP servers Coffer aggregates behind one endpoint. See [MCP servers](/guides/mcp-servers). |
| Capabilities | **Custom tools** | `/custom-tools` | HTTP API requests your agents call as tools — see [Custom tools](/guides/custom-tools). |
| Capabilities | **Skills** | `/skills` | The skill library Coffer delivers to agents. Each skill has **Files**, **Delivery**, **Requires** and **History** tabs. See [Skills](/guides/skills). |
| Capabilities | **CLIs** | `/clis` | The command-line tools your skills need, and whether each is installed — see [CLIs](/guides/clis). |
| Context | **Knowledge** | `/knowledge` | Collections of documents under `~/.coffer/vault/knowledge/`: one tree beside a read-only reader that opens a document in your editor, a **Tidy** button on each collection and **Tidy all**, and a **Document** and a **History** tab on every document. See [Knowledge](/guides/knowledge). |
| Context | **Memory** | `/memory` | What your agents learned, read from their own memory and turned into one note per subject: the partitions, with a search by name and path and **Tidy** on each partition (**Tidy all** for every one). A partition's page has **Memories** and **Delivered** tabs. See [Memory](/guides/memory). |
| System | **Secrets** | `/secrets` | Every stored secret with what uses it: add, replace, delete, add the values that are missing on this Mac, answer approvals. See [Secrets](/guides/secrets). |
| System | **Activity** | `/activity` | What changed, what agents called and what the daemon logged: **Everything** merged into one stream, then **Changes**, **Tool calls** and **Daemon log**. See [Activity and audit](/guides/activity). |
| System | **Sync** | `/sync` | Converging this vault with a git remote you own, as **Status**, **Machines** and **Remote** tabs, with **Review changes to push** (`/sync/pending`), **Resolve conflicts** (`/sync/conflicts`) and **Review held deletions** (`/sync/deletions`) views, each a file list beside the chosen file's diff. See [Vault sync](/guides/vault-sync). |

In Chinese the groups read 智能体 · 运行 · 能力 · 上下文 · 系统, and an agent is always called 智能体.

An entry that belongs to an [experimental feature](/guides/experimental-features) is marked **Experimental** beside its page's title and in **Settings › Features**; the sidebar row itself carries no tag, and on the collapsed rail its tooltip reads **Knowledge · Experimental**. While the feature is switched off it looks absent: the entry is left out of the sidebar, a group whose entries are all switched off loses its heading too, and following a link to its page shows the standard not-found page. Knowledge, Memory, Sync and Model providers (with its Usage tab) are the four.

**No badges.** The sidebar carries no counts or dots: everything that needs you is listed under **Needs you** on **Overview**, and the desktop app's menu bar shows the same count.

**The title bar.** In the desktop app, one thin strip in the sidebar's colour runs across the top of the window. It holds the window's traffic lights, the **sidebar toggle** and the **back and forward arrows**, and nothing else. In a browser there is no strip: the Coffer mark and the sidebar toggle sit at the top of the sidebar, and the browser's own Back and Forward do the navigating.

**Back and forward.** The arrows (**⌘[** and **⌘]**) move through the pages you have visited in the app and grey out when there is nowhere to go. No page carries its own back button or "back to list" link; the arrows are the only way back, and they also close a detail page you opened from a list.

**Collapsing and resizing.** The sidebar toggle (**⌘\\**, **Ctrl+\\** on other systems) collapses the sidebar to a 56-pixel icon rail and brings it back; the choice is remembered. While expanded, drag the thin line on its right edge to make it wider or narrower (see [Resizing split views](#resizing-split-views)).

**Page layout.** Every page is padded 16 pixels at the top and 32 on the sides. The page header has the title on the left, its actions on the right and one line of explanation under it. Inside a page, a bordered box holds a group of things (a list of rows, a table), while a thing's own properties sit as plain rows separated by hairlines, without a box around them.


## Overview

**Overview** is the page the app opens on. It answers "is everything OK, and what needs me?" in three parts:

- **Needs you**: one row per problem across every area, most severe first and then oldest. Each row names the thing it is about (a server, an agent, a channel, the vault's sync), gives the reason in a sentence and since when, and has one button that opens the page, or the tab, where you deal with it. The button says what it does for that kind of problem (**Reconnect channel**, **Review held changes**, **Add secret**, **Repair hook**) behind a small icon, and a long reason wraps to two lines, with the whole text on hover. A memory hook that was changed by hand in an agent's settings and that Coffer could not rewrite opens that agent's **Hooks** tab with **Repair hook**. Testing an MCP server again or re-checking a command runs right in the row: the button turns into a disabled **Retrying…** or **Checking…**, a blue line says what is starting, and the row leaves the list once the problem is gone (it returns to its button if the problem is still there). Connecting an agent, repairing its files and the other actions that change something outside Coffer keep opening their page, where the change is previewed. The list is the daemon's attention list (`GET /api/v1/attention`). Rows clear themselves: the page follows the daemon's event stream, so a row disappears as soon as its problem is resolved. If one area could not be checked, the page says so above the rows, because anything that area would report is missing. The prompt is the same one the item's page offers; **Hand off to &lt;Agent&gt;** needs a Coffer-managed agent. Every row, whatever its severity, has one main button, the split button **Hand off to &lt;Agent&gt; ▾** (it starts your hand-off agent in your preferred terminal with the prompt as its first message; its menu holds **Hand off to** the other agent and **Copy prompt**, a fix prompt for an agent outside Coffer) and a **⋯** menu with **Ignore**. An ignored item disappears from Overview and the menu bar's count; Coffer remembers the choice on this Mac (not synced to your other machines) and changes nothing about the agent. The ignored item's own page shows a muted line under its header ("… — ignored on Overview"), with **Show it again** to bring it back to Overview. The page's banner **×** is this same **Ignore**, and what you ignored returns by itself when the situation changes (a different set of conflicts, say). Secrets add two rows: "N secrets have no value on this Mac" (**Open Secrets**) and "N changes waiting for approval" (**Review**, which opens the approvals dialog). The list shows about six rows and scrolls inside its frame. When nothing needs you, a calm card says so, with one sentence on what is fine ("Both agents are connected, 12 servers are answering and your vault is in sync.") and when it last checked. **Recent activity** leaves out changes to anything belonging to an experimental feature that is switched off.
- **Health**: a tile per area: Agents, MCP servers, Skills, Knowledge, Memory, Model providers, Channels, Sync, Custom tools, CLIs, Secrets and Usage (which opens the Usage tab of Model providers). Each shows a status word, a count and a one-line summary and opens the area's page. Agents and Channels count "1 of 2 connected" (a reconnecting channel is named with its time); MCP servers show the calls and errors of the last 24 hours; Knowledge shows its collections and when one was last edited; Memory shows when it was last updated; Sync shows when its last round ended and how many commits it is behind and ahead; a CLI that needs attention is worded by what is wrong ("1 not logged in"); Secrets nothing uses read as plain "2 unused"; Usage shows the last 24 hours' tokens, cost and each provider's share. A tile that fails to load says what failed, shows the failed request, and offers **Retry** and a link to its page, and the rest of the page keeps working.
- **Recent activity**: the last few changes, with a link to [Activity](/guides/activity).

Before any agent is registered, Overview opens on connecting one instead. It lists the agents Coffer supports, each with its config folder and whether it was found on this machine. The found ones are ticked, and **Review and connect** shows every file change before Coffer writes anything. If none was found, it says so and offers **Scan again**, and each agent row reads **Not found** with an **Install ↗** link to that agent's official install page. **Add an agent by hand** opens the Agents page, and below comes the first step for each thing agents share.

## Search or jump to

The **Search or jump to…** control at the top of the sidebar opens the command palette; so does **⌘K** (**Ctrl+K**) from anywhere. Type a few letters, move with the arrow keys, press **Enter** to go there, **Escape** to close and return to where you were.

The palette is for navigation only — it takes you to pages and objects and never runs an action; actions stay on their page. It finds:

- **Pages** — every sidebar entry and every Settings tab. Pages are always available, even while the daemon is offline.
- **Objects** — your agents, model providers, conversations, channels, MCP servers, custom tools, skills, CLIs, knowledge collections, memory partitions and secrets, matched by name (and by title on the kinds that carry one), each with a status word where its list has one (**Failing**, **Off**, **Missing**); a skill's row also names the agents it is delivered to (**Skill · Claude Code · Codex**). Each kind loads on its own: while they load the palette says so, and if one fails only that kind shows an error. While the daemon cannot be reached, the palette lists Pages only and says that objects need the daemon.

With nothing typed it shows **Recent** — the last few things you opened from it, remembered in this browser — above every page. Once you type, the single best hit leads as **Best match** (an exact name first), then the other matching pages, then the matching objects grouped by kind in sidebar order. A query that matches nothing says so.

Pages and objects of a switched-off [experimental feature](/guides/experimental-features) are left out, as they are everywhere else in the UI.

## The sidebar footer

The bottom of the sidebar holds, top to bottom:

- **Update ready** — in the desktop app, when a newer version has been found: a card naming it with **Restart** (downloads it, checks its signature, installs it and reopens Coffer) and **What's new** (Settings › About). Dismiss it and it comes back at the next launch; it is never a popup.
- **Settings** — a gear and the word **Settings** (tooltip **Settings ⌘,**). It always opens **Settings › General**, and is highlighted while the window is open. On the collapsed rail it is the gear alone.

The footer shows nothing about the daemon and has no version menu. Trouble with the daemon is shown where you cannot miss it: a **Reconnecting…** bar over the page while the connection is coming back, and a full offline page, with **Restart daemon** in the desktop app, when it is gone. Theme and language live only in **Settings › General**; the version and **Check for updates** are in **Settings › About**.

## Settings

Settings opens as a large window over the page you are on, so closing it puts you back exactly where you were. Open it with the **Settings** row, with **⌘,** (**Ctrl+,**) when you are not typing in a field, or from the palette. Every field saves as you change it; there are no Save buttons. Each tab opens with a title and one line of explanation, and its sections are plain headings with a one-line description, hairline-separated rows and generous space between sections, not boxes. Dialogs offer a quiet **Cancel** beside the main action.

It has six tabs, in this order:

| Tab | Address | What it holds |
| --- | --- | --- |
| **General** | `/settings/general` | **Appearance** — **Language** and **Theme** (Light, Dark or System) — **Tables and files** — **Open files with** (the app Coffer opens managed files with) — **Preferred terminal** (the terminal an opened conversation or session resumes in: the system default, a terminal Coffer detected, or a custom command with `{cwd}` and `{command}`) and **Hand-off agent** (Claude Code or Codex, for the hand-off button) — **Check skills for updates** (how often this machine checks Git-imported skills for newer commits: **Every 6 hours**, the default, **Every day**, **Every week** or **Only when I ask**; kept on this machine only, not synced, effective at once; a skill's own **Check for updates** works in every setting) — and **Speech to text**: a provider and model that transcribe voice messages, with **Test**, an inline not set / answering / failing state. The upkeep passes Coffer runs by itself are switched from the automatic-read schedule on the Memory page (the **▾** on **Update memory**). While the Models feature is off, the connection choice is left out. |
| **Security** | `/settings/security` | Only what belongs to this Mac. **Encryption**: where the master key lives (the macOS Keychain, with nothing to move) and **Back up the master key** (desktop app only). **Access**: the daemon's access token, hidden until **Show**, with **Copy** and **Rotate…**. **Approvals**: whether a secret waits for your approval before it goes somewhere new, and **Review** for what waits. Stored secrets are on the [Secrets](/guides/secrets) page, not here. |
| **Data** | `/settings/data` | What Coffer keeps, by kind. **Vault** — the git repository of your configuration, skills, knowledge and encrypted secrets: its size, how many versions it holds, and **Open folder** (hover it to see the path). Each file's versions are in the vault's git history (`git log -- <path>` in the folder **Open folder** reveals), and a skill's or a knowledge document's in its **History** tab (see [Editing the vault by hand](/guides/vault-files)). **Local content** — channel attachments, which are not synced: back that folder up yourself, or let them expire: its **Attachments** row keeps them for 30 days by default (**Keep forever** or a number of days; shortening asks first and says how many files the next cleanup deletes). **History** — how long **Changes**, **Tool calls** and **Skill working files** (the logs, journals and temporary files skills write under `~/.coffer/skill-data`) and **Config backups** (the copies Coffer keeps of an agent's config file before rewriting it; the newest of each file is always kept) are kept (**Keep forever** or a number of days; shortening asks first and says how many records, or files, the next cleanup deletes), cleaned up every six hours, with **Clear expired data now** (which also clears expired attachments). **Rebuildable cache** — the memory tree: **Clear** asks first, and memory is rebuilt from the agents' own memory on the next update. |
| **Daemon** | `/settings/daemon` | The daemon's status — its state and address, how long it has been up, its pid and how many agents are connected to Coffer — with **Restart** — in the desktop app the app restarts it; in a browser the daemon restarts itself and the page reloads from the new one. **Startup**: **Start at login** (macOS) and **Port** (1024–65535, default 38470). The port applies when you press Enter or leave the field; a port another program holds, or one outside the range, is refused in place. An applied port reads **takes effect after Coffer restarts**, with **Restart now**, which in a browser reloads the page from the new port; agents reconnect to it on their own. While the daemon is offline the tab names how to bring it back and the controls are disabled. There is no token here (it is on Security) and no stop control. |
| **Features** | `/settings/features` | The four [experimental features](/guides/experimental-features) — Knowledge, Memory, Sync and Model providers — one list, each with a one-line description and an on/off switch that saves at once. A write that fails says **Couldn't save the change** under the row. A feature pinned by `COFFER_FEATURES` has its switch disabled. |
| **About** | `/settings/about` | The version with **Copy diagnostics for a bug report** beside it (version, host, daemon state and port, enabled features — never a token or a secret); **Details**: the version with the commit a release was built from, license, source and the data folder. In the desktop app, **Updates**: when Coffer last checked, **Check for updates**, a newer version with **Download and restart**, and **Check automatically** (see [Desktop app → Update](/guides/desktop-app#update)). In a browser it says updates are installed by the desktop app, and offers **Copy prompt** / **Hand off to &lt;Agent&gt;** to hand upgrading this copy of Coffer to your agent. |

**Each tab has its own address.** Opening a tab changes the URL to `/settings/<tab>`, so a bookmark or a shared link opens that tab directly. Close the window with **×**, **Escape**, a click outside it or the browser's **Back** button: you return to the page underneath, at its own address. If you load a `/settings/<tab>` address fresh, it opens over **Overview**, and closing it lands on `/`.

The theme, preferred editor, preferred terminal and hand-off agent are stored in your browser and never sent to the daemon, except as the target when you open a file. Stopping the daemon is CLI-only (`coffer daemon stop`): stopping it from the page would take the page down with it. Rotating the access token is on **Settings › Security**; the page installs the new token and keeps working, and other open tabs and clients using the old one stop until they load the new one. Revealing or copying a secret, backing up the master key and approving a pending [approval](/guides/secrets#approvals) exist only in the [desktop app](/guides/desktop-app#presence-checks-and-approvals), because each needs a Touch ID or password check a browser cannot run; a browser tab shows **Open in Coffer app** in their place.

### Preferred terminal and hand-off agent {#preferred-terminal}

Two choices under **Settings › General › Tables and files** decide where an agent opens when Coffer hands you off to it: a conversation or session row (**Open in &lt;terminal&gt;**), the hand-off button (**Hand off to &lt;Agent&gt;**), and **Tidy** and **Tidy all** on Knowledge and Memory. Both are kept in this browser, like **Open files with**.

**Preferred terminal** is built like the preferred editor:

- **System default** is the platform's own terminal. On macOS it is Terminal; on Linux Coffer tries `x-terminal-emulator`, `gnome-terminal` and `konsole`.
- The terminals Coffer detects on this machine are listed by name: on macOS Terminal, iTerm, Warp and Orca, on Linux GNOME Terminal and Konsole.
- **Custom command** takes a command template for a terminal Coffer does not list. Write `{cwd}` where the working directory goes and `{command}` where the agent command goes, for example `mycterm --workdir {cwd} -e {command}`. Coffer splits the template into arguments and runs it directly, not through a shell, so quoting a placeholder is not needed.

The first time Coffer drives Terminal or iTerm, macOS asks whether Coffer may control it (an Automation permission). Allow it. If you refused, turn it back on under **System Settings › Privacy & Security › Automation**, or pick another terminal.

**Hand-off agent** is the agent the hand-off button starts: Claude Code or Codex. The button reads **Hand off to &lt;Agent&gt;** with that agent's name, and its ▾ menu offers the other agent when it is installed, and **Copy prompt**. With no managed agent only **Copy prompt** is offered. Pressing the button asks for no confirmation: the terminal opens in the right directory and the agent starts with the prompt as its first message. The prompt reaches the agent through a private temporary file, never the command line or your shell history, and the agent runs under its own permission mode, so you can read what it was asked and stop it with Esc or Ctrl-C.

If the terminal cannot be started, a toast says why. **Copy prompt** and, on a session row, **Copy command** always work.

## Resizing split views

Wherever the window is split side by side — the sidebar against the page, the Knowledge tree against its reading pane — the two halves are divided by a thin line you can drag. The line lights up in the accent colour while you hover over or drag it.

- **Drag** it to resize. **Double-click** it to go back to the default width.
- **From the keyboard**, tab to the line and press **←** or **→** to move it in small steps.
- **Limits keep both sides usable.** The sidebar stays between 200 and 300 pixels wide (220 by default). A list is at least 240 pixels and at most half the split, and the detail beside it keeps at least 480.
- **Widths are remembered per page, in this browser.** It is a convenience only: another browser, the desktop app or a private window starts from the defaults, and nothing is sent to the daemon.

## Light and dark

The UI follows your system's light or dark appearance, and switches with it as it changes. To pick one yourself, choose **Light** or **Dark** in **Settings → General → Theme**; **System** goes back to following the system. The choice applies at once and is kept in `localStorage` under `coffer.theme`, so each browser and the desktop app keep their own. See [Design system](/architecture/design-system) for how the two themes are built.

## Language

Switch between **English** and **简体中文** in **Settings → General → Language**. Every label changes immediately, with no reload, and the choice is kept in `localStorage` under `coffer.language`. The About tab has no language control.

## Conventions every page shares

**URLs describe what you are looking at.** A refresh, a bookmark or a shared link reopens the same view. A detail page's tab is part of its path: the default tab is the bare address, any other tab adds its name — `/mcp-servers/github` and `/mcp-servers/github/tools`. Skills and MCP servers are addressed by their name, which is fixed once registered (`/skills/release-notes`), and an agent by its type, since there is one per type (`/agents/claude_code/skills`). Kinds you can rename — model providers, channels, knowledge collections, memory partitions — are addressed by their immutable uid (`/channels/<uid>/<tab>`), so a rename does not break a link. Activity, Sync and Model providers' Usage still carry their tab as `?tab=` (`/activity?tab=mcp` — Everything is the bare `/activity` — `/sync?tab=remote`, `/model-providers?tab=usage`), and Activity and Usage keep their search, range and filters there too, and an open file in a tree is `?file=`. The Conversations list's filters are search parameters (`/conversations?source=local|<channel uid>&agent=codex&q=sentry`, where `local` is This Mac).

**Lists look and behave alike.** Every list page uses one table, and clicking anywhere on a row opens its detail page (a switch, a menu or a checkbox in the row does its own job instead). Every row action is labelled.

- **Filters** sit in one row: the search first (press `/` to jump to it), then pills, then **Clear filters** while anything is set. They show no result counts.
- **Sorting** is on number and time columns only, three-state: press a header once for one direction, again for the other, a third time to go back to the page's own order.
- **Lists** show whole; there is no page-size setting and no button to load more. A list that can grow very long (activity, conversations, agent sessions, sync rounds) loads the next page by itself as you scroll to its end, and the page says how many are loaded.
- **Times** read relative while they are recent ("3 h ago") and as a date ("Aug 12") after that.
- **Selecting** rows uses the header checkbox for the whole list. A bar over the table reads "N of M selected" with the actions that apply, there is no select-all inside it, and **Esc** clears the selection.
- **Details** that open beside a list open in one right-hand drawer over a dimmed page, 640 pixels wide until you drag its left edge (double-click the edge to reset); **Esc**, a click outside or its ✕ closes it and focus returns to the row.

**Handing a problem to an agent.** Installing, setting up, logging in and troubleshooting depend on the machine, so Coffer hands them to an agent instead of printing commands. The hand-off is one split button, **Hand off to &lt;Agent&gt; ▾**: the button starts your default hand-off agent (**Settings › General › Hand-off agent**, Claude Code or Codex) in your preferred terminal with the prompt sent as its first message, with no confirmation. The prompt reaches the agent through a private temporary file, never the command line or shell history. The ▾ menu holds **Hand off to** the other agent, when it is available, and **Copy prompt** for an agent outside Coffer, which answers with a "Prompt copied" toast. With no Coffer-managed agent installed only **Copy prompt** is offered. What Coffer can do itself stays a button (**Retry**, **Check again**, **Test**).

**Banners can be ignored.** A banner at the top of a page for something that needs you has an **×**. It does the same as **Ignore** on Overview: the item goes from the page, Overview and the menu bar's count, the page's header then reads "… — ignored on Overview. Show it again", and the item comes back by itself when the situation changes.

**Reach is one control.** Resources that agents consume carry a **Reach** button on their detail page and, in a table, a badge on their row (the MCP servers and Skills lists put the button on the open item): **Off**, **All agents** or **Chosen agents** (the list can never be emptied: the last ticked agent stays ticked, and to reach nobody you turn the resource **Off**). **All agents** includes agents you add later. The choice is saved the moment you change it, with "Applying…" and then "✓ Saved" in the panel, and applies to this machine only. Select several rows to set reach for all of them at once. For a channel, reach means the agents it may drive; see [Channels](/guides/channels#default-agent-and-scope). Knowledge collections and memory partitions carry no reach or status control at all: each is always served to every agent.

**Things save as you change them.** Settings, reach and model providers apply the moment you choose. The web UI has no document editor, so no **Save** button and no question when you leave a page: a skill's `SKILL.md`, a knowledge document, a memory and an agent's config file are shown read-only, with **Open in editor** and **Reveal in Finder**, and you change them in your own editor (**Settings › General**) or ask your agent to.

**A list's search matches names.** The search box over a list of named things (servers, tools, skills, channels, providers, secrets…) matches each item's name, and its title where it has one — never its description, endpoint or path — so what it finds is what you see in the row. Searches over records, such as Activity and conversations, match their text.

**Empty, loading and error states are explicit.** An empty list shows a welcome card with one next step, such as **Add server**. A loading list keeps its header over skeleton rows. A failed request shows a readable message, never a generic error code. On a page with a list beside a detail (MCP servers, Skills, CLIs, Channels, Custom tools, Model providers, Knowledge) each state sits where it belongs: a list that cannot load shows **Couldn't load …** in the list pane, under the filter, with **Retry**, **Open daemon log** (Activity › Daemon log) and the failed request (`GET path · status · trace id`) to paste into a bug report; a filter that matches nothing says **No server matches "terraform"** with **Clear filter**; and an address whose object no longer exists shows **This server no longer exists** with the address, when it was last seen in the audit log, **Back to MCP servers** and **View in Activity**.

**An unknown path shows a not-found page.** Any address the app does not answer shows a not-found page with the sidebar intact: it names the address, suggests the closest page when one is close (**Did you mean /mcp-servers**), and offers **Back to Overview** and **Search Coffer ⌘K** (the palette).

File trees and previews — on the skill, knowledge and agent pages, and a memory partition's list — fill the window to the bottom and scroll inside. Inside a file viewer, **Cmd+F** (**Ctrl+F**) searches the file.

## When the daemon is not reachable

The UI checks the daemon every 30 seconds. When it stops answering, the UI retries after 1, 2, 4 and 8 seconds and shows what is happening at the top of the workspace, while the sidebar stays usable:

| State | When | What you see |
| --- | --- | --- |
| **Reconnecting to the daemon…** | The first 10 seconds after it stopped answering (**Connecting to the daemon…** if it never answered). | The page stays where it was, dimmed and paused, under a bar that counts the attempts and says nothing is lost, with **Retry now**. |
| **Coffer's daemon isn't running** | After that. | The page makes way for a screen naming the address the UI talks to, when it checks next and when the daemon last answered, with **Retry**, the `coffer daemon start` command to copy and, in the desktop app, **Open daemon log**, which opens the log file in your system viewer; in a browser the screen shows `coffer log daemon` to copy instead (the Activity page needs the daemon). |
| **Daemon out of date** | The desktop app attached to a daemon left running by an earlier version. Desktop app only. | A bar over the page with **Restart daemon**. |
| **Coffer needs git** | The daemon answers but waits for git: none is installed, or it is older than 2.40. | Every page makes way for one screen saying what is wrong and that the vault keeps its history and syncs with git, with **Copy prompt** (a prompt for your agent to install or update git) and **Check again**, which restarts the daemon once git is there and carries on into the app. See [Coffer needs git](/guides/troubleshooting#coffer-needs-git). |

The recovery the offline screen offers depends on the host. Both hosts show the command to run, `coffer daemon start` (**Or start it from a terminal**), because a page cannot start a daemon; the desktop app also shows **Start daemon**. Either way the screen clears itself when the daemon answers again, with no reload: every list is read again and a **Reconnected** notice appears.

## Related

- [Desktop app](/guides/desktop-app) — the same UI in a native macOS window.
- [Running the daemon](/guides/daemon) — ports, login service and lifecycle.
- [App shell](/architecture/app-shell) — why the sidebar is grouped the way it is, and how Settings, the palette and the footer are built.
- [Security model](/architecture/security) — why the token lives in the page and what the host check protects.
- [Spec: web-ui](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/web-ui/spec.md)
- [A Per-Start Token, Handed to the Page by Whoever Hosts It, Behind a Loopback Host Guard](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/daemon-auth-and-origin-guard.md)
