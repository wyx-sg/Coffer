# Coffer UI Visual Language

> Companion reference for agents touching `frontend/`. The authoritative
> tokens live in [`frontend/tailwind.config.js`](../../frontend/tailwind.config.js);
> this file documents the conventions.

## Source of truth

`frontend/tailwind.config.js` is the single source of truth for spacing,
colour, radius, typography, and container width tokens. Do not introduce
parallel CSS variables or ad-hoc inline style values; extend the Tailwind
config and reuse the tokens.

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
  resource list and the daemon-offline banner).

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
  render with no content while data resolves. Give each surface its own
  empty/loading/error treatment (e.g. `components/chat/ChatEmptyState.tsx`);
  there is no shared `EmptyState` primitive yet — factor one out when a
  second feature needs the same shape.
- Status surfaces (daemon offline, capability disabled, tool-call health)
  use the `status.*` tokens; do not pick raw `green/amber/emerald` palette
  classes. Type sizes come from the built-in scale (`text-sm`/`text-xs`/…),
  never per-component `text-[Npx]`.

## When in doubt

If a token does not exist yet, extend the Tailwind config in the same PR
that needs it and explain the addition in the PR description. Do not
inline magic numbers.
