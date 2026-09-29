---
title: App shell
description: How the web UI's frame is organised — the sidebar grouped by intent, one list of names and routes, Settings as an addressable modal, the daemon footer, the navigation-only palette, attention dots, resizable splits and tab addresses — and why each works the way it does.
---

# App shell

The app shell is the frame every page of the web UI sits in: the sidebar, the command palette, the Settings window, the daemon footer and the split views. None of it is a feature of its own, but every feature is reached through it, so its rules decide whether the product feels like one thing or like fifteen pages stitched together. This page explains those rules and the reasons behind them. For how to use the shell, see the [Web UI guide](/guides/web-ui).

## Principles

- **Group by intent, not by implementation.** The sidebar is organised around what a person comes to do, not around how Coffer stores things.
- **One name, one route, everywhere.** A surface is named and addressed once, and every place that shows it reads that one definition.
- **Every view is an address.** What you are looking at — a page, a tab, the Settings window over a page — is in the URL, so a refresh, a bookmark or the Back button brings it back.
- **One source per fact.** The footer and the offline banner read the same daemon status; the palette reads the same lists the pages read. Two readings of one fact would eventually disagree.
- **The shell renders; capabilities decide.** The shell draws attention dots, gates experimental entries and lays out splits, but whether something needs attention or is switched on is decided by the capability that owns it.

## The sidebar is grouped by what you come to do

The sidebar has fifteen entries: **Overview** on top under no heading, then five groups.

| Group | Entries | The question it answers |
| --- | --- | --- |
| Agents | Agents, Model providers | Which agents do I have, and which models do they run on? |
| Run | Conversations, Channels | How do I put an agent to work — directly or from IM? |
| Capabilities | MCP servers, Custom tools, Skills, CLIs | What can my agents do? |
| Context | Knowledge, Memory | What do my agents know? |
| System | Secrets, Activity, Usage, Sync | How do I look after Coffer and what every part shares? |

The earlier sidebar grouped by role — agents as consumers, a large Resources group of what they consume, and System. It was accurate, but it was the architecture's view: a person looking for "where do I add a tool" had to know that tools, skills, knowledge and channels are all resources. Grouping by intent puts the answer under the question. It also keeps every group short: none has more than four entries, so each heading is scannable at a glance, and the rule that no group passes five tells the next change where a new entry belongs or when the grouping must be revisited.

Two placements follow from intent rather than from type. **Model providers** sits with Agents because a provider is each agent's model configuration, chosen on the agent's page. **Conversations and Channels** stay two entries in one group: Conversations is every conversation Coffer runs, whatever started it, and Channels is only setup and connection status.

**Overview** belongs to no group because it summarises all of them, and it is the landing page at `/`. **Settings** is not an entry at all (see [below](#settings-is-a-modal-with-an-address)).

The alternatives — keeping the role groups, one big Resources group, a flat list, or fewer entries with more tabs — are argued in the decision record [The Sidebar Is Grouped by What the Person Comes to Do](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sidebar-grouped-by-what-the-person-comes-to-do.md).

### Experimental entries

Knowledge, Memory and Sync are experimental features. The sidebar does not decide whether one is on; it asks the feature switch and follows it. A switched-off feature's entry is left out entirely rather than greyed, a group left with no entries drops its heading, and a switched-on one carries an **Experimental** marker so its status is never a surprise. Features are switched on the command line, so a switched-off page's notice states the fact and offers no link to a setting that does not exist.

## One list of names and routes

Three surfaces show the app's map: the sidebar, the palette's Pages group and the Settings window's tab strip. They all read one list that defines every entry and every Settings tab — its route, its icon, its label and the experimental feature it belongs to, if any.

That single list is what makes the principle "one name everywhere" hold without effort. A surface reached from the sidebar and from the palette cannot end up with two names, because there is only one place the name is written. The same goes for the Chinese labels: each surface has one English and one Chinese name, and in Chinese an agent is always 智能体. Renaming a surface, or adding one, is a change to that list, and every surface follows.

## Settings is a modal with an address

Settings opens as a large window over the page you were on, from the labelled **Settings** row in the sidebar footer, from **⌘,** (**Ctrl+,**), or from the palette. It has five tabs grouped by what they manage — General, Security, Data, Daemon and About.

Settings is a modal rather than a page because it is visited briefly and then left. As a page it took a sidebar slot and, worse, navigated you away: after changing the theme you had to find your way back to what you were doing. As a modal it keeps the page you came from underneath, so closing it is a return rather than a second journey.

A modal that is only state, though, cannot be linked to, reloaded or reached with Back. So Settings is also a route: each tab lives at `/settings/<tab>`, and the page you opened it over is remembered as the **background location**. The rules follow from that:

- **Opening** moves the URL to the tab's address and records the page underneath, which keeps rendering at its own route.
- **Closing** — with **×**, **Escape**, a click outside, or the browser's **Back** — returns to the background page's own address, exactly as it was.
- **A fresh load** of `/settings/<tab>` has no page underneath to return to, so it opens over Overview, and closing lands on `/`.
- **Old addresses redirect** to where their content now lives, so a bookmark from before the regrouping still opens something sensible.

The **Settings** row is highlighted only while the modal is open. It is labelled with the word, not just a gear, because an icon alone at the foot of a long list is easy to miss; on the collapsed rail, where there is no room for words, the gear carries a tooltip.

## The footer reads the same status as the banner

Below the Settings row, the footer names the daemon's state in plain words: connecting, running on its port, stopping, or offline. Clicking it opens **Settings → Daemon**.

The web UI already polls the daemon's status to decide when to show the [offline banner](/guides/web-ui#when-the-daemon-is-not-reachable). The footer reads that same poll and adds no timer of its own. This is not only economy: two timers would sample the daemon at different moments and could briefly disagree, with the banner saying offline while the footer still says running. Reading one source, and checking for a failure before trusting a cached answer, makes that impossible — the footer never reads as running while the banner is up.

The footer reports; it does not ask you to act. Coffer starts its daemon by itself, so the state is there for reassurance and diagnosis, and the banner stays the one place that names a recovery.

## The palette is navigation only

**⌘K** (**Ctrl+K**) or the **Search or jump to…** control opens the command palette. It lists **Pages** — every sidebar entry and Settings tab — and **Objects** — agents and the resources of every listed kind, matched by name (and by title on the kinds that carry one).

- **It only navigates.** Choosing an item opens a page; nothing in the palette creates, deletes or changes anything. Actions stay on the pages that own them, next to the context that makes them safe.
- **It adds no search route.** Each kind's objects come from the same list query that kind's page already uses, so the palette reuses whatever is cached and fetches only what is not. There is no aggregate index that could fall behind the pages.
- **Each kind stands alone.** Every kind loads on its own; one still loading says so in its group, and one that fails shows its own error while the others keep working.
- **Pages never need the daemon.** They come from the one list of names and routes, so the palette is useful even while the daemon is offline; it then lists Pages only and says that objects need the daemon.
- **It respects feature switches.** Pages and objects of a switched-off experimental feature do not appear.

## Attention signals belong to their capability

An entry whose kind needs you carries a small dot — a dot rather than a count, because the sidebar's job is to say *where* to look, and the page says how much. The dot stays visible on the collapsed rail.

The shell owns only the drawing. Whether a kind needs attention, and what clears it, is decided by the capability that owns the kind: today only Sync raises a signal, while a vault is held or failed, and visiting Sync clears it. The shell keeps one map from sidebar entry to signal, and a kind that wants a dot adds its signal to that map; the sidebar then marks it with the same dot and no other change. A signal that has not loaded, or whose read failed, simply shows no dot — the sidebar is never the place an error surfaces.

## Split views are resizable, per browser

The sidebar against the page, and the conversation list against the open conversation, are split views divided by a hairline you can drag. Every split behaves the same way:

- The divider has a wider invisible grip than the line it draws, and lights up in the accent on hover or drag.
- Double-clicking restores the default, and the arrow keys move a focused divider in small steps, so resizing does not require a mouse.
- Limits keep both sides usable: a sidebar between 200 and 300 pixels, a list at least 240 pixels and at most half the split, a detail pane at least 480.
- The width is remembered per page in this browser only.

Widths are a per-browser convenience, not state. They are never sent to the daemon, never synced, and if the browser blocks storage the split simply opens at its default. Nothing about what you are looking at depends on them. The sidebar's other convenience, collapsing to a 56-pixel icon rail, is remembered the same way.

## Tabs live in the path

A detail page's tab is part of its address: the default tab is the bare path and every other tab adds its name, `/<kind>/<id>/<tab>`. A tab is a place you can be, so it is addressed like one — a link can land on it and Back steps between tabs you visited. Secondary state, such as which file is open in a tree, stays a query parameter.

Which identifier fills `<id>` depends on whether the kind can be renamed:

- **Skills and MCP servers** are addressed by their **name**, because the name is fixed once registered and is what you already recognise — `/mcp-servers/github/tools`.
- **Kinds you can rename** — model providers, channels, knowledge collections, memory partitions — are addressed by their immutable **uid**, so renaming never breaks a link.

Old addresses — a tab given as `?tab=`, or a skill or MCP server addressed by uid — redirect to the current form. Pages not yet rebuilt, such as an agent's page, still carry their tab as `?tab=` until their turn comes.

## Related

- [Web UI guide](/guides/web-ui) — using the sidebar, palette, Settings and split views.
- [Design system](/architecture/design-system) — the tokens and shared components the shell is drawn with.
- [Distribution and releases](/architecture/distribution#experimental-features) — how experimental features are switched.
- [The Sidebar Is Grouped by What the Person Comes to Do](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sidebar-grouped-by-what-the-person-comes-to-do.md)
- Spec: [web-ui](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/web-ui/spec.md)
