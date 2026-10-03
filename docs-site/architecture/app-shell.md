---
title: App shell
description: How the web UI's frame is organised — the sidebar grouped by intent, one list of names and routes, Settings as an addressable modal, the title bar and its history arrows, the connection states, the navigation-only palette, attention badges, resizable splits and tab addresses — and why each works the way it does.
---

# App shell

The app shell is the frame every page of the web UI sits in: the sidebar, the command palette, the Settings window, the title bar and the split views. None of it is a feature of its own, but every feature is reached through it, so its rules decide whether the product feels like one thing or like fifteen pages stitched together. This page explains those rules and the reasons behind them. For how to use the shell, see the [Web UI guide](/guides/web-ui).

## Principles

- **Group by intent, not by implementation.** The sidebar is organised around what a person comes to do, not around how Coffer stores things.
- **One name, one route, everywhere.** A surface is named and addressed once, and every place that shows it reads that one definition.
- **Every view is an address.** What you are looking at — a page, a tab, the Settings window over a page — is in the URL, so a refresh, a bookmark or the Back button brings it back.
- **One source per fact.** The reconnecting bar and the offline page read the same daemon status; the palette reads the same lists the pages read. Two readings of one fact would eventually disagree.
- **The shell renders; capabilities decide.** The shell draws attention badges, gates experimental entries and lays out splits, but whether something needs attention or is switched on is decided by the capability that owns it.

## The sidebar is grouped by what you come to do

The sidebar has fourteen entries: **Overview** on top under no heading, then five groups.

| Group | Entries | The question it answers |
| --- | --- | --- |
| Agents | Agents, Model providers | Which agents do I have, and which models do they run on? |
| Run | Conversations, Channels | How do I put an agent to work — directly or from IM? |
| Capabilities | MCP servers, Custom tools, Skills, CLIs | What can my agents do? |
| Context | Knowledge, Memory | What do my agents know? |
| System | Secrets, Activity, Sync | How do I look after Coffer and what every part shares? |

The earlier sidebar grouped by role — agents as consumers, a large Resources group of what they consume, and System. It was accurate, but it was the architecture's view: a person looking for "where do I add a tool" had to know that tools, skills, knowledge and channels are all resources. Grouping by intent puts the answer under the question. It also keeps every group short: none has more than four entries, so each heading is scannable at a glance, and the rule that no group passes five tells the next change where a new entry belongs or when the grouping must be revisited.

Two placements follow from intent rather than from type. **Model providers** sits with Agents because a provider is each agent's model configuration, chosen on the agent's page. **Conversations and Channels** stay two entries in one group: Conversations is every conversation Coffer runs, whatever started it, and Channels is only setup and connection status.

**Overview** belongs to no group because it summarises all of them, and it is the landing page at `/`. **Settings** is not an entry at all (see [below](#settings-is-a-modal-with-an-address)).

The alternatives — keeping the role groups, one big Resources group, a flat list, or fewer entries with more tabs — are argued in the decision record [The Sidebar Is Grouped by What the Person Comes to Do](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sidebar-grouped-by-what-the-person-comes-to-do.md).

### Experimental entries

An entry can belong to an [experimental feature](/guides/experimental-features). The sidebar does not decide whether one is on; it asks the feature switch and follows it. A switched-off feature's entry is left out entirely rather than greyed, a group left with no entries drops its heading, and its **Experimental** mark sits beside the page's title and in Settings › Features, not on the sidebar row (the collapsed rail's tooltip still says so). Knowledge belongs to `knowledge`, Memory to `memory`, Sync to `sync`, and Model providers (with its Usage tab) to `models`; every other entry, Conversations and Channels included, is always there. A deep link into a switched-off feature's page lands on the not-found page, and its sections inside other pages are left out the same way, with no notice and no switch-on button. Settings has a tab of its own for the switches, **Features**, in every build.

## One list of names and routes

Three surfaces show the app's map: the sidebar, the palette's Pages group and the Settings window's tab strip. They all read one list that defines every entry and every Settings tab — its route, its icon, its label and the experimental feature it belongs to, if any.

That single list is what makes the principle "one name everywhere" hold without effort. A surface reached from the sidebar and from the palette cannot end up with two names, because there is only one place the name is written. The same goes for the Chinese labels: each surface has one English and one Chinese name, and in Chinese an agent is always 智能体. Renaming a surface, or adding one, is a change to that list, and every surface follows.

## Settings is a modal with an address

Settings opens as a large window over the page you were on, from the **Settings** row in the sidebar footer, from **⌘,** (**Ctrl+,**), or from the palette. It has six tabs grouped by what they manage — General, Security, Data, Daemon, Features and About. Each tab follows the page grammar below: a title and one intro line, then plain sections, and every control saves as you change it.

Settings is a modal rather than a page because it is visited briefly and then left. As a page it took a sidebar slot and, worse, navigated you away: after changing the theme you had to find your way back to what you were doing. As a modal it keeps the page you came from underneath, so closing it is a return rather than a second journey.

A modal that is only state, though, cannot be linked to, reloaded or reached with Back. So Settings is also a route: each tab lives at `/settings/<tab>`, and the page you opened it over is remembered as the **background location**. The rules follow from that:

- **Opening** moves the URL to the tab's address and records the page underneath, which keeps rendering at its own route.
- **Closing** — with **×**, **Escape**, a click outside, or the browser's **Back** — returns to the background page's own address, exactly as it was.
- **A fresh load** of `/settings/<tab>` has no page underneath to return to, so it opens over Overview, and closing lands on `/`.

The **Settings** row always opens the General tab and is highlighted only while the modal is open. It is labelled with the word, not just a gear, because an icon alone at the foot of a long list is easy to miss; on the collapsed rail, where there is no room for words, the gear carries a tooltip.

## The title bar carries the controls that belong to the window

In the desktop app, one 44-pixel strip in the sidebar's colour runs across the whole window. It holds the native traffic lights, the **sidebar toggle** (**⌘\\**) and the **back and forward arrows** (**⌘[** and **⌘]**), and nothing else. With the sidebar open, the sidebar's edge line runs up through the strip; collapsed, a 56-pixel icon rail sits under it and badges shrink to dots. In full screen the lights are hidden and the controls move to the left edge. A browser draws no strip: the Coffer mark and the toggle sit at the top of the sidebar, and the browser's own arrows navigate.

The arrows walk the app's own history, so no page needs a back button of its own. A per-page "back to the list" link would be a second, competing meaning of "back" — and one that disagrees with the arrows whenever you arrived somewhere else — so pages carry none, and a detail opened from a list returns with the arrows. Page content sits 16 pixels below the strip and 32 pixels in from the sides, the same on every page.

The sidebar footer shows no daemon state and has no version menu. Coffer starts its daemon by itself, so a permanently visible running dot only added noise; what you need to know is when something is wrong, and that is shown in the workspace itself. Theme and language are preferences and live with the other preferences in **Settings › General**; the version and **Check for updates** are in **Settings › About**, and an available update is offered by a card above the footer.

The web UI polls the daemon's status every 30 seconds. One piece of the shell watches that poll: when it fails it retries after 1, 2, 4 and 8 seconds and publishes one connection phase — ok, reconnecting or offline — that every other part reads. The reconnecting bar and the offline page read that same phase and add no timer of their own: two timers would sample the daemon at different moments and could briefly disagree. Reading one source, and checking for a failure before trusting a cached answer, makes that impossible.

## Losing the daemon keeps the page

A daemon that restarts, or a laptop waking from sleep, drops the connection for a few seconds. Replacing the page with an error at the first failed probe would throw away what the user was reading and typing for a gap that heals itself. So for the first 10 seconds of failures the page stays mounted, dimmed and inert, under a **Reconnecting…** bar with **Retry now**; only after that does it make way for the offline screen that names the host's recovery — the `coffer daemon start` command in a browser, **Start daemon** in the desktop app. When the daemon answers again every query is read again and a **Reconnected** notice says so. Both states are drawn in the workspace, not floating over it, so the sidebar and the Settings window stay usable throughout.

## The palette is navigation only

**⌘K** (**Ctrl+K**) or the **Search or jump to…** control opens the command palette. It finds **Pages** — every sidebar entry and Settings tab — and **Objects** — agents and the resources of every listed kind, matched by name (and by title on the kinds that carry one). With nothing typed it shows the last few choices (**Recent**, kept in the browser) above every page; under a query the best hit leads, then pages, then objects grouped by kind.

- **It only navigates.** Choosing an item opens a page; nothing in the palette creates, deletes or changes anything. Actions stay on the pages that own them, next to the context that makes them safe.
- **It adds no search route.** Each kind's objects come from the same list query that kind's page already uses, so the palette reuses whatever is cached and fetches only what is not. There is no aggregate index that could fall behind the pages.
- **Each kind stands alone.** Every kind loads on its own; while they load the palette says so, and one that fails shows its own error while the others keep working.
- **Pages never need the daemon.** They come from the one list of names and routes, so the palette is useful even while the daemon is offline; it then lists Pages only and says that objects need the daemon.
- **It respects feature switches.** Pages and objects of a switched-off experimental feature do not appear.

## Attention signals belong to their capability

An entry whose kind needs you carries a count badge — always the same red, capped at **9+** — and on the collapsed rail a dot of the same colour, with the count in the icon's tooltip. The sidebar speaks only through these badges, and only for things that need you: failures, drift, a held vault, a required CLI that is missing; items you ignored on Overview are not counted. An informational count — how many servers there are, how many documents wait in a knowledge collection's inbox — never becomes a badge, because a sidebar full of numbers stops saying where to look.

The shell owns only the drawing. Whether a kind needs attention, and what clears it, is decided by the capability that owns the kind: Agents, MCP servers, Skills and Channels count what the daemon's cross-kind attention list (the list Overview's **Needs you** shows) reports for them; Sync keeps its own signal, cleared by visiting Sync; CLIs count the required commands that need you. The shell keeps one map from sidebar entry to signal, and a kind that wants a badge adds its signal to that map; the sidebar then marks it with the same badge and no other change. A signal that has not loaded, or whose read failed, simply shows no badge — the sidebar is never the place an error surfaces.

## Split views are resizable, per browser

The sidebar against the page, the conversation list against the open conversation, the Knowledge tree against its reading pane and a memory partition's list against the open memory are split views divided by a hairline you can drag. Every split behaves the same way:

- The divider has a wider invisible grip than the line it draws, and lights up in the accent on hover or drag.
- Double-clicking restores the default, and the arrow keys move a focused divider in small steps, so resizing does not require a mouse.
- Limits keep both sides usable: a sidebar between 200 and 300 pixels, a list at least 240 pixels and at most half the split, a detail pane at least 480.
- The width is remembered per page in this browser only.

Widths are a per-browser convenience, not state. They are never sent to the daemon, never synced, and if the browser blocks storage the split simply opens at its default. Nothing about what you are looking at depends on them. The sidebar's other convenience, collapsing to a 56-pixel icon rail with the title-bar toggle, is remembered the same way.

## Tabs live in the path

A detail page's tab is part of its address: the default tab is the bare path and every other tab adds its name, `/<kind>/<id>/<tab>`. A tab is a place you can be, so it is addressed like one — a link can land on it and Back steps between tabs you visited. Secondary state, such as which file is open in a tree, stays a query parameter.

Which identifier fills `<id>` depends on whether the kind can be renamed:

- **Skills and MCP servers** are addressed by their **name**, because the name is fixed once registered and is what you already recognise — `/mcp-servers/github/tools`.
- **Kinds you can rename** — model providers, channels, knowledge collections, memory partitions — are addressed by their immutable **uid**, so renaming never breaks a link.

An unknown tab segment falls back to the bare address. A knowledge collection's pane is addressed the same way — `/knowledge/<uid>/history?file=<document>` for a document's History, `/knowledge/<uid>/inbox` for its Inbox — and a memory partition's Delivered tab is `/memory/<uid>/delivered`. A list page with no detail to nest under, such as Sync or Activity, carries its tab as `?tab=` instead; the default tab is the bare address.

A list's filters are query parameters too, because a filtered list is something you link to. The Conversations list is the one that needs it most: `/conversations?source=seatalk&agent=codex` narrows it by source and agent, and a channel links to its own conversations as `/conversations?channel=<uid>`. The filters stay on the address when a conversation opens beside the list (`/conversations/<id>?channel=<uid>`), and the draft that **New conversation** opens is `/conversations/new` — a place, but not yet a conversation: the first send creates the row and moves the address to its id.

## Related

- [Web UI guide](/guides/web-ui) — using the sidebar, palette, Settings and split views.
- [Design system](/architecture/design-system) — the tokens and shared components the shell is drawn with.
- [Distribution and releases](/architecture/distribution#experimental-features) — how experimental features are switched.
- [The Sidebar Is Grouped by What the Person Comes to Do](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sidebar-grouped-by-what-the-person-comes-to-do.md)
- Spec: [web-ui](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/web-ui/spec.md)
