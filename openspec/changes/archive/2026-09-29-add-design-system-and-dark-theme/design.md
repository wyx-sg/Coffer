## Context

The Foundations boards (design canvas ① "Foundations & Shell") are the approved
source: `ds/coffer/tokens.json` names every colour, radius, size, type style,
duration and z-index, and one board per component family (buttons, inputs,
selection, status, feedback, overlays, lists, tooltips, focus, motion, agent
badge, reach, change preview, brand) specifies geometry and states. This change
puts that system into the running app without restructuring the shell or any
page — that is the next piece of work (UI1), and it will be compared against the
screenshot baseline this change records.

## Decisions

### Token names are the Foundations role names

CSS variables carry the `tokens.json` names exactly (`--surface-raised`,
`--text-muted`, `--accent-soft`, `--danger-strong` …) and Tailwind exposes the
same names (`bg-surface-raised`, `text-text-muted`, `bg-accent-soft`,
`bg-danger-strong`). One name for one role, from the board to the class.

Values are RGB channels (`67 83 216`) wrapped by Tailwind as
`rgb(var(--x) / <alpha-value>)`, so the opacity modifiers the pages already use
(`bg-destructive/10`) keep working. The boards' dark status tints are
translucent (`rgba(76,183,130,.12)`); they are stored flattened over `surface`
so every colour stays a channel value. The scrim and the shadows are the only
full colour strings, and nothing applies an opacity to them.

### The shadcn names stay as aliases — except `accent`

`--background`, `--card`, `--primary`, `--muted-foreground`, `--destructive`,
`--status-ok|warn|err` … are re-pointed at the Foundations roles, so every page
written against them changes look without changing code. The one exception is
`accent`: in shadcn it meant the hover wash, in Foundations it is the indigo.
Keeping both meanings under one name would make `bg-accent` mean two things, so
the handful of pages that used it as a hover wash now say `bg-surface-hover`,
and `accent` means the indigo everywhere.

### The type scale is re-pointed at the Foundations roles

`text-2xs` 11 (label), `text-xs` 12 (meta), `text-sm` and `text-base` 13 (body),
`text-md` 15 (dialog title), `text-lg` 18 (page title), `text-xl` 20 (detail
title), `text-display` 32 (brand only); weights add `font-book` 450,
`font-label` 550, and `font-bold` becomes 650. Radius names follow the tokens:
`rounded-xs` 4 … `rounded-md` 7 (controls) … `rounded-xl` 10 (cards),
`rounded-2xl` 12 (dialogs). The pages' existing classes therefore land on the
new scale; the serif display face is gone.

### Theme resolution happens in script, not in CSS

`<html data-theme>` always holds the resolved theme. `src/lib/theme.ts` resolves
the preference (`system` by default) against `prefers-color-scheme` before the
first render and follows the media query while the preference is `system`; CSS
only knows `[data-theme="dark"]`, so the dark values are written once. The
desktop shell's CSP forbids inline scripts, so there is no pre-paint snippet; the
one frame before the module runs paints the dark surface for a dark-system
viewer through a media-query fallback on `html:not([data-theme])`.

The picker lives in Settings › General — the tab that already holds the display
preferences. The Foundations shell places it in the sidebar's version menu; it
moves there with the shell (UI1).

### Fonts are files in the source tree

The woff2 files are copied from the npm packages `@fontsource-variable/figtree`
and `@fontsource-variable/jetbrains-mono` (5.3.0, OFL-1.1) into
`src/assets/fonts/` with their licences, Latin and Latin Extended subsets only,
and declared by `@font-face` in `index.css`. Vite fingerprints and emits them
next to the bundle, so they are served from the page's own origin in the browser
and inside the desktop shell. They are source files rather than a runtime
dependency so the screenshot baseline cannot change under a dependency bump.

### Brand marks are shipped as supplied

`src/assets/brand/` holds the Claude Spark (Clay) and OpenAI Blossom (black,
white) SVGs byte for byte as supplied. The colour gate scans `.ts`, `.tsx` and
`.css` only, so the marks' own fills are not "colour literals". The Coffer Stroke
C mark is drawn in markup from the Brand board's path with `currentColor` and the
accent token, so it themes like any other component.

### Geometry follows the boards, not a restatement of them

The spec states behaviour and leaves geometry to the Foundations boards. Where
a value written down while building differed from the board, the board wins —
for example the change preview's diff rows are 18px as drawn, not the 20px an
earlier note restated.

### The screenshot baseline has its own daemon

The visual project runs from `e2e/playwright.visual.config.ts` against a fresh
isolated daemon and its own Vite port, never the functional suite's daemon, so
what earlier specs created cannot leak into a screenshot. Each route is shot at
1280×800 in light and dark (`emulateMedia({ colorScheme })`, so the "system"
path is what is exercised), with animations disabled, the caret hidden, fonts
awaited and time-dependent text masked. Baselines are per platform; CI writes a
missing platform's baselines instead of failing and uploads them, and compares
once they are committed.

## Risks / Trade-offs

- Pages were laid out for 14px body text and 40px controls; at 13px and 30px
  some will look sparse or misaligned until their own redesign. The baseline
  records exactly that starting point.
- Flattened dark tints are a hair off the boards where a tint sits on a raised
  surface rather than the page surface.
