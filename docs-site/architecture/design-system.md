---
title: Design system
description: How the Coffer web UI draws every surface from one set of theme tokens — the colour roles, light and dark, the type and geometry scales, the shared components, and the rules that keep them from drifting.
---

# Design system

The web UI and the desktop app render the same frontend, and every surface in it is drawn from one small design system. This page explains the ideas behind it: why colours are roles rather than values, how light and dark work, what the type and geometry scales are for, which shared components carry the product's recurring ideas, and how the build keeps all of it from drifting. It is for anyone changing the UI, and for anyone who wants to know why Coffer looks the way it does. The visual source of truth is the **Foundations** board set on the design canvas; this page describes how the running app follows it.

## Principles

Six rules decide between two designs that both work. The one that follows more of them wins.

- **Attention first.** A page leads with what needs you. Healthy things stay quiet; a failing server or a held sync round rises to the top.
- **One accent.** Indigo means "this is the action" or "this is selected" and nothing else.
- **Status is a dot and a word.** Never colour alone: the dot always sits beside the word it means, so the state survives colour-blindness and a greyscale screenshot.
- **Identifiers in mono.** Anything you could paste into a terminal — a path, a port, a tool name, an environment key, a commit id — is set in JetBrains Mono. Prose is in Figtree.
- **No dead ends.** Every empty, error and offline state names its next step: a button, a command to copy, or a link to the place that fixes it.
- **Quiet chrome, dense content.** Hairlines instead of boxes, shadows only on what floats, 13px text on a 4px grid. The developer's data is the loudest thing on screen.

## Colours are roles, not values

A component never asks for a colour. It asks for a **role**: the page surface, a raised surface such as a card or an input, a sunken well, the hover and selected fills, the border and the finer hairline, primary / muted / subtle text, the accent with its soft fill and its text form, the four status colours (success, warning, danger, neutral) each with a soft tint, and a few control roles (the chip and agent-badge tile, the switch track, the code fill, the focus ring, the scrim behind dialogs).

Each role is defined once per theme, in one stylesheet. That is what makes a theme switch free: nothing in a component knows which theme is on screen, because the roles it names are re-pointed underneath it. It is also why the roles are few and named for their job. "Muted text" is a decision already made — it passes contrast on every surface in both themes — whereas a grey value is a decision each component would have to make again.

Two consequences follow:

- **Colour is reserved for meaning.** The accent marks action, focus and selection. Success, warning and danger mark state and are never borrowed for decoration, and the accent is never used for state. A healthy status therefore reads in muted text; only a problem is coloured.
- **A literal is a bug.** A hex value, an `rgb()` or `hsl()` value or a Tailwind palette class in a component is a colour that will not follow the theme. The build rejects one anywhere outside the token stylesheet (see [Keeping it from drifting](#keeping-it-from-drifting)).

The names the UI was first written against (shadcn's `background`, `card`, `primary`, `muted-foreground` and so on) still work: each is an alias of the role it now means. New work uses the role names.

## Light and dark

Every role has a light and a dark value. The dark theme is charcoal rather than black, and its surfaces step up in lightness as they rise — a card is one step lighter than the page — so depth reads without shadows. The accent is a touch deeper in dark so white labels on it keep their contrast, and the text form of the accent is lighter so links stay readable.

By default the UI follows the operating system's appearance, and follows it live when the system switches. The viewer can override it — System, Light or Dark — on the General tab of Settings. That choice is a display preference of the browser or app window, like the interface language: it is kept locally and never sent to the daemon, so two machines, or the browser and the desktop app, can each look the way their viewer prefers.

## Type

The app runs on one base size, **13px**, and builds hierarchy from weight and colour rather than from size jumps. There are a handful of roles: the page title (18, bold), the title of the object a detail page is about (20), a dialog or empty-state title (15), a section title (15, semibold, with one visible description line under it in 12 muted), body text (13), buttons and row titles (13 at a medium-heavy weight), meta lines (12, muted), and captions such as table heads and group labels (11, semibold). Nothing is set below 11px. Numbers use tabular figures, so columns of counts line up.

Two families are used: **Figtree** for the interface and **JetBrains Mono** for identifiers. Both are open-source (SIL Open Font License) and both are **bundled with the app**. The desktop shell only allows fonts from the app's own origin, and a tool that runs on your machine should not reach out to a font service to draw its own screen, so the font files ship inside the build.

## Geometry

Everything sits on a **4px grid**. Controls have three heights — 26 inside rows and toolbars, 30 as the default for every button, input and select, 36 for full-page states — and share one radius. Radii grow with the surface: the smallest marks (a checkbox, a key cap) are the tightest, controls a little rounder, cards rounder again, and dialogs and the command palette roundest.

There is exactly **one real shadow**, and it belongs to things that float over the page: menus, popovers, dialogs, toasts and the palette. Cards and panes are flat with a hairline. When a page needs more separation, it gets more space, not more elevation.

Motion confirms cause and effect and never decorates. There are three durations — fast for hover, press and every exit, a base for menus and page fades, slow for dialogs and toasts entering — and four curves. With the system's reduced-motion setting on, transforms are dropped, fades are shortened and loops stop.

Keyboard focus is always visible and only appears for keyboard focus, never on a mouse click: a two-pixel accent ring with a gap, following the control's shape; text fields show an accent border with a soft halo instead.

Waiting is shown where it happens and only when it lasts. A button that started an action keeps its width and label, swaps its icon for a small spinner and reads busy rather than disabled; a list that is loading keeps its header and fills with skeleton rows shaped like the real ones. Both appear only after a short delay, so an answer that comes back quickly never flashes a spinner. A tooltip only names an icon-only control (its name, and its shortcut when it has one) or shows the full text of something truncated. A button or menu item that carries words gets no tooltip, and a tooltip never explains what will happen: that belongs in a menu item's second line or behind a "?" hint. Tooltips never hold actions: one opens after a moment of hover, at once on keyboard focus, and the next one opens without the wait while the pointer moves along a toolbar.

## Shared components

The base controls — button, input, select, checkbox, switch, tabs, dialog, tooltip, popover, table, card, toast, skeleton, banner — are the design system's primitives, and pages are built from them rather than restyling their own. Above them sit a few components that carry ideas the whole product repeats. Each exists so one question has one answer everywhere.

**Agent badge.** How an agent is shown in compact form: its official mark on a neutral tile — Claude Code by the Claude Spark, Codex by the OpenAI Blossom beside the word "Codex" — and never letters. Every agent sits on the same tile, so colour outside the mark stays reserved for state: a healthy badge is plain, and only a problem adds a mark (a warning dot for an agent not connected to Coffer, a dashed outline for one not installed). A badge without its name beside it carries the name and state in its label and tooltip. Agents always appear in the order of the Agents page, so a position means the same agent everywhere.

**Status dot and word.** Four states — running, degraded, failing, disabled — each a coloured dot beside its word. In a list row it is quiet; in a detail header it becomes a tinted pill.

**Reach.** "Who can use this resource?" is always one of three answers: Off, All agents, or Chosen agents. The same control sits in a list row, a detail header and a selection bar, and shows the chosen agents' badges so the answer can be read without opening it. Reach belongs to this machine and is never synced.

**Change preview.** Before Coffer writes into files it does not own — repairing drift, connecting an agent, resolving a sync conflict — it can show the change first, in one preview: grouped by agent and by file, each file with its operation and line counts, a plain-words sentence per agent of what will happen, and the diff as the proof underneath. It has a state for every moment — computing, nothing to change, ready, applying, applied, and failed partway. When some changes fail, it stays open, says what did apply, and retries only the rest.

**Empty state.** A tile, a title, one line of why, and one next action. An error in place of a list uses the same shape, toned for danger, with a retry and a way to diagnose.

**Lists and tables.** Most pages are lists of hairline-separated rows. A table is used only where the reader compares columns — agents side by side, usage by provider, activity over time: sentence-case heads with no fill, rows tall enough for a sub-line, a ticked row reading as selected, a floating selection bar that lists safe actions before destructive ones, and no numbered pages: a long list shows its first rows with "Showing x of y" and grows with **Load N more**, N being the page size set in Settings.

**Page grammar.** Every page is built from the same few shapes so it reads at a glance. A bordered box holds a *group of things* — a list of rows, a table, a set of cards. One thing's own properties are plain rows separated by hairlines, with no box. A page opens with its title, its actions on the right and one line of explanation; each section under it has a title and one visible description line, with generous space between sections. Explanations are shown, not tucked behind a "?", which is kept for the overflow of a long one. Pages carry no back button: the title bar's back and forward arrows are the only way through history. Counts that mean "needs you" are one red and stop at 9+. Controls save as you change them; only editors of documents have an explicit Save.

**Split view.** Every list-and-detail, tree-and-file and list-and-thread page can be resized by dragging its divider, and so can the sidebar. The divider is a hairline until the pointer reaches it, is a keyboard stop that arrow keys move, resets on a double-click, and remembers its width for this viewer.

**Pickers.** A time range (a recent period or a custom range) for anything measured over time, and a folder for anything that runs in a directory: the chosen path in mono beside a Choose… button, and a folder that has since moved shown in error with the old path still visible.

**The Coffer mark.** An open rounded square drawn with the navigation icons' own pen around a single accent dot — the product drawn from its own UI. It is the sidebar's brand and the browser tab's icon, and it follows the theme like everything else.

## Keeping it from drifting

A design system decays one convenient exception at a time, so the rules that matter are enforced by the build rather than by review:

- **No colour literals.** `make lint` fails on a hex value, a colour function or a Tailwind palette class anywhere in the frontend source outside the token stylesheet.
- **Small components.** Each component file stays under a line budget, so a component that grows a second job gets split rather than absorbing it.
- **A screenshot baseline.** Every top-level page is captured in light and dark and compared on demand, with fonts fixed and animation off so the comparison is stable. A change that moves pixels shows up as an image diff to review, and an intended one updates the baseline in the same change.

The engineering conventions for applying all this in code — the token class names, which primitive to reach for, how tests assert on components — live in the repository's contributor notes (`.agents/visual-language.md` and `.agents/frontend.md`).
