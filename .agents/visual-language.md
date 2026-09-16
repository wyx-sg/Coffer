# Coffer UI Visual Language

> Companion reference for agents touching `frontend/`. The authoritative
> tokens live in [`frontend/tailwind.config.js`](../frontend/tailwind.config.js);
> this file documents the conventions.

## Source of truth

`frontend/tailwind.config.js` is the single source of truth for the tokens it
actually defines — `colors`, `borderRadius`, `fontFamily`, `maxWidth`, and the
`container` — and this file is the source of truth for the vocabulary built on
them. It extends **no** `spacing` and **no** `fontSize` key: spacing and the type
scale are Tailwind's own defaults, used as-is (§Spacing, §Typography). Do not
introduce parallel CSS variables or ad-hoc inline style values; extend the
Tailwind config and reuse the tokens.

## Colour palette

All semantic colours are HSL variables (`hsl(var(--name))`) resolved per
theme. The redesign is light-only.

Semantic tokens (defined in `tailwind.config.js` `theme.extend.colors`):

- `background` / `foreground` — page base.
- `card` / `card-foreground` — card surface and text on it.
- `popover` / `popover-foreground` — dropdowns, dialogs.
- `primary` / `primary-foreground` — primary actions ("Add MCP server",
  "Save").
- `secondary` / `secondary-foreground` — secondary actions, inactive tabs.
- `muted` / `muted-foreground` — disabled / placeholder text.
- `accent` / `accent-foreground` — hover and selected states.
- `destructive` / `destructive-foreground` — delete / remove actions.
- `border`, `input`, `ring` — surface borders, form input borders, focus
  ring.
- `status.ok` / `status.warn` / `status.err` — health pills (used by the
  resource list and the daemon-offline banner). Components reach them only
  through `frontend/src/lib/statusColors.ts`.
- `highlight` / `highlight-active` — the row / item that a search or a
  selection is pointing at, and the one currently active; the only tokens for
  "this is the one you are looking at".

Pick from the semantic name, not the underlying hue. Adding a new
semantic token is preferred over hard-coding hex / hsl values inside a
component.

## Typography

`fontFamily.sans` is the default UI face (system stack, Inter / Roboto
fallback). `fontFamily.serif` is reserved for long-form prose (Source
Serif). `fontFamily.mono` is reserved for code, command snippets, and
identifiers (`SFMono-Regular` / `Menlo` fallback).

Use Tailwind's built-in type scale (`text-sm`, `text-base`, `text-lg`,
`text-xl`, `text-2xl`) rather than per-component pixel sizes. Headings
inside a screen step through the scale in single increments; do not skip
levels.

## Spacing

Stay on Tailwind's default 4 px scale (`p-4`, `gap-6`, `space-y-3`, …).
The `container` utility centres content with `2rem` padding and a `2xl`
breakpoint at 1400 px. `maxWidth.content` (72 rem) caps a workbench page;
`maxWidth.prose` (60 ch) caps long-form text.

## Radius

`borderRadius.lg` / `md` / `sm` / `xl` are derived from `--radius` so a
single root variable retunes the whole UI. Use `rounded-lg` for cards,
`rounded-md` for buttons / inputs, `rounded-sm` for inline chips.

## Composition rules

- Build screens from shadcn primitives in `frontend/src/components/ui/`
  rather than inventing new wrappers per page.
- Empty / loading / error states are first-class — never let a screen
  render with no content while data resolves. `components/EmptyState.tsx` is
  the shared empty-state primitive (icon, title, description, action) — use
  it for every list / not-found / zero-result screen. Loading keeps the
  surface's real shape with `components/ui/skeleton.tsx`: a `DataTable` given
  `isLoading` renders skeleton rows under its mounted header, and a detail
  page renders a `Skeleton` title rather than a blank or a "Loading…" card.
- A non-fatal caution (a config that works but is unusual, a reach that
  names no agent) is the `warning` variant of `Alert` — status-warn border
  and icon on a card background — not a destructive alert and not a toast.
- Status surfaces (daemon offline, capability disabled, tool-call health)
  use the `status.*` tokens; do not pick raw `green/amber/emerald` palette
  classes. Type sizes come from the built-in scale (`text-sm`/`text-xs`/…),
  never per-component `text-[Npx]`.
- The sidebar is always present. At `md` and above it expands to a labelled
  rail and can be collapsed; below `md` it is the icon-only rail, so a narrow
  viewport keeps its navigation rather than losing it behind a drawer.

## When in doubt

If a token does not exist yet, extend the Tailwind config in the same PR
that needs it and explain the addition in the PR description. Do not
inline magic numbers.
