# Coffer UI Visual Language

> Companion reference for agents touching `frontend/`. The design source is
> the **Foundations** board set on design canvas 0 "Foundations"
> (its `ds/coffer/tokens.json` names every token). The running values live in
> [`frontend/src/index.css`](../frontend/src/index.css) (colours, per theme) and
> [`frontend/tailwind.config.js`](../frontend/tailwind.config.js) (the names
> Tailwind exposes); this file documents how to use them. The ideas behind the
> system are on the docs site: `docs-site/architecture/design-system.md`.

## Source of truth

- **Colours** are CSS variables in `src/index.css`, one block for light
  (`:root`) and one for dark (`:root[data-theme="dark"]`), stored as RGB
  channels so Tailwind's `/opacity` modifiers work. That file is the only place
  in `frontend/src` a colour literal may appear —
  `scripts/check_frontend_colors.py` (in `make lint`) fails on a hex value, an
  `rgb()`/`hsl()` value that is not `rgb(var(--token))`, or a Tailwind palette
  class (`bg-red-500`, `text-white`) anywhere else.
- **Everything else** (radius, type, weights, shadows, motion, z-index, fixed
  sizes) is a Tailwind theme key in `tailwind.config.js`.
- A value the boards define that has no token yet: add the token (to both
  themes, if it is a colour) in the same change. Never inline a magic number.

## Colour roles

Utility names are the Foundations role names.

| Role | Classes | Use |
| --- | --- | --- |
| Surfaces | `bg-surface`, `bg-surface-sidebar`, `bg-surface-raised`, `bg-surface-sunken`, `bg-surface-hover`, `bg-surface-selected`, `bg-surface-footer` | page · sidebar · cards, inputs, menus, dialogs · wells, skeleton, segmented track · hover fill · selected row / current nav / pressed · dialog footer band |
| Lines | `border-border`, `border-border-subtle` | control borders and pane dividers · hairlines between rows |
| Text | `text-text`, `text-text-muted`, `text-text-subtle` | primary · secondary, meta, healthy status words · placeholders, icons, group labels only (never on selected, chip or soft fills) |
| Accent | `bg-accent`, `text-accent-foreground`, `bg-accent-soft`, `text-accent-text` | the one indigo: primary action, focus, selection — never status |
| Status | `success`, `warning`, `danger`, `neutral`, each with `-soft`; `bg-danger-strong` + `text-on-status`; `text-warning-foreground` | dot, word, icon · tinted pill or banner fill · solid destructive fill and count badges |
| Controls | `bg-chip`, `bg-control-off`, `bg-knob`, `bg-code`, `ring-focus-ring`, `bg-scrim` | chip and agent-badge tile · switch off · switch knob · code fill · focus ring · behind dialogs only |

The shadcn names the pages were written against — `background`, `foreground`,
`card`, `popover`, `primary`, `secondary`, `muted`, `muted-foreground`,
`destructive`, `input`, `ring`, `status.ok|warn|err` — are **aliases** of these
roles and keep working; new code uses the role names. **`accent` is the
indigo**, not shadcn's hover wash: hover is `bg-surface-hover`.

Health and status tones reach components through `src/lib/statusColors.ts`
and the `StatusWord` / `StatusPill` components; components never pick a status
colour for decoration, and the accent is never a status.

`highlight` / `highlight-active` are the find-in-preview match colours.

## Light and dark

There is **no `dark:` variant** anywhere in `src`. `<html data-theme>` always
holds the resolved theme (`src/lib/theme.ts`: System follows
`prefers-color-scheme` live, Light / Dark are the viewer's override in
`localStorage coffer.theme`), and the token blocks re-point every role under
`[data-theme="dark"]`. A component that uses roles is already themed. The rare
asset that must differ per theme (the OpenAI Blossom mark, black on light and
white on dark) switches with the arbitrary variant `[[data-theme=dark]_&]:…`.

## Typography

Figtree (`font-sans`, the default) for the interface, JetBrains Mono
(`font-mono`) for anything you could paste into a terminal — paths, ports, tool
names, env keys, ids. Both are bundled (`src/assets/fonts/`, OFL); never add a
font from a CDN (the desktop shell's CSP is `font-src 'self' data:`).

The app runs on **13px**; hierarchy comes from weight and colour, not size.

| Role | Classes |
| --- | --- |
| Page title | `text-lg font-bold` (18/24, 650) |
| Detail title | `text-xl font-bold` (20/26) |
| Dialog / empty-state title | `text-md font-bold` / `text-md font-semibold` (15/20) |
| Section title | `text-sm font-semibold` (13/18, 600) |
| Body | `text-sm` (13/19) — `text-base` is the same size |
| Buttons, row titles, labels | `text-sm font-label` (550); field labels `text-xs font-label` |
| Meta, help, status words | `text-xs text-text-muted` (12/16) |
| Caption: group labels, table heads | `text-2xs font-semibold` (11/14) |
| Mono | `font-mono text-xs` (12); chips `font-mono text-2xs` (11) |

Weights: `font-normal` 400, `font-book` 450 (idle nav and tabs), `font-medium`
500, `font-label` 550, `font-semibold` 600, `font-bold` 650, `font-heavy` 700
(count badges). Never below 11px; never `text-[Npx]`. Numbers are tabular
everywhere (set on `body`). Sentence case everywhere; uppercase only for captions.

## Spacing and sizes

A 4px grid on Tailwind's default scale (`p-2.5` = 10px). Page padding 40 top /
24 sides on a phone and 40 from `md` up (`Layout`); section gap 24; card padding 16; dialog padding 20. Fixed geometry:
`h-control-sm` 26 (in rows, banners, toolbars), `h-control-md` 30 (every
default control), `h-control-lg` 36 (full-page states, onboarding); `min-h-row`
40 list rows (56 with a sub-line), `min-h-setting-row` 56; `w-sidebar` 220,
`w-rail` 56. Widths: `max-w-form` 960 (forms, settings), `max-w-measure` 720
(reading), `max-w-empty` 360 (empty-state body), `max-w-content` 72rem (a
workbench page).

## Radius

Radii grow with the surface: `rounded-xs` 4 (kbd, checkbox, skeleton),
`rounded-sm` 5 (chip, agent badge, segment), `rounded-item` 6 (nav item, pill,
tooltip, menu item), `rounded-md` 7 (buttons, inputs, selects), `rounded-lg` 8
(list rows, banners, code blocks, icon tiles), `rounded-xl` 10 (cards, toasts,
menus, popovers), `rounded-2xl` 12 (dialogs, the palette), `rounded-full`
(switch, count badges, dots).

## Elevation, motion, focus

- One real shadow, `shadow-overlay`, for what floats (menus, popovers, dialogs,
  toasts, palette); it carries its own 1px ring, so no border. `shadow-lifted`
  is the active segment only; `shadow-knob` the switch knob. Cards and panes
  are flat: a hairline, no shadow.
- Motion: `duration-fast` 120 (hover, press, knob, tooltip, every exit),
  `duration-base` 180 (menus, scrim, page fade), `duration-slow` 240 (dialog,
  toast, palette enter); `ease-out` entering, `ease-in` leaving,
  `ease-standard` moving. Reduced motion drops transforms and loops
  (`index.css`).
- Focus is keyboard-only (`focus-visible:`): 2px `ring-focus-ring` with a 2px
  offset over the surface; text fields use `border-accent` plus a 3px
  `ring-accent-soft` halo; full-bleed rows an inset ring.
- z-order: `z-sticky` 10, `z-dialog` 50, `z-menu` 55 (above the dialog, so
  a select or menu opened inside one is not under its scrim), `z-toast` 60,
  `z-tooltip` 70. Disabled: `opacity-disabled` (.45); a disabled text field
  `opacity-field-disabled` (.6) so its value stays selectable.

## Composition rules

- Build screens from the primitives in `src/components/ui/` and the shared
  components above them — `AgentBadge` / `AgentBadgeGroup`
  (`components/agent/`), `StatusWord` / `StatusPill` (`components/status/`),
  `ReachControl` (`components/reach/`), `ChangePreview`
  (`components/change-preview/`), `EmptyState`, `CofferMark`
  (`components/brand/`). Do not restyle a primitive per page.
- An agent is shown by its **official mark** (`AgentBadge`), never letters or
  a colour of its own; order agents as the Agents page does.
- Status is always a **dot plus its word**; a healthy word is muted, a
  problem's word takes its status colour.
- Empty / loading / error states are first-class: `EmptyState` for every
  list / not-found / zero-result screen (tone `error` for a failed list, with
  retry); loading keeps the surface's shape with `Skeleton`; a `DataTable`
  given `isLoading` renders skeleton rows under its mounted header.
- A non-fatal caution is the `warning` `Alert` (banner) — not a destructive
  alert and not a toast. Banners carry one action.
- Tooltips name things; they never hold an action or the only copy of
  important information.

## Screenshot baseline

Every top-level route is captured in light and dark by the `visual`
Playwright project (see [`testing.md`](./testing.md) "Visual baseline"). A
change that moves pixels on purpose updates the baseline in the same PR, and
the image diff is reviewed like code.
