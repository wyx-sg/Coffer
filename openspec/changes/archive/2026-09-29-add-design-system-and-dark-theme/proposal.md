## Why

The web UI was drawn in one light-only palette (cream paper, clay accent) with
the system font, and its colours were half tokens, half literals scattered
through components. The approved Foundations boards on the design canvas define
Coffer's visual language for the final product: a neutral surface family with
one indigo accent, four status colours that are never borrowed for anything
else, Figtree at 13px with JetBrains Mono for identifiers, fixed control
geometry, one overlay shadow, and a dark theme for every token. Every later page
redesign builds on that system, so it has to be in place first — in the tokens,
in the base components and in a screenshot baseline that shows what each page
looks like before the page work starts.

## What Changes

- The Foundations colour roles become the theme tokens in `frontend/src/index.css`,
  defined once for light and once for dark; the shadcn names the pages were
  written against stay as aliases of those roles, so every existing page picks up
  the new look without being rewritten.
- The UI follows the operating system's light / dark appearance by default and
  lets the viewer override it (System / Light / Dark) from Settings › General.
  The choice is this browser's own display preference (`localStorage
  coffer.theme`); the page renders the resolved theme as `data-theme` on
  `<html>`.
- A colour literal (hex, `rgb()` / `hsl()`, or a Tailwind palette class)
  anywhere in `frontend/src` outside `index.css` fails `make lint`.
- Figtree and JetBrains Mono (both SIL OFL 1.1) are bundled into the build and
  served from the app's own origin, so the desktop shell's `font-src 'self'`
  policy never blocks them and nothing is fetched from a font CDN.
- The base components (`frontend/src/components/ui`) are restyled to the
  Foundations spec: control heights 26 / 30 / 36, radius 7 on controls, the
  accent focus ring, the overlay shadow on everything that floats.
- New shared components: the **agent badge** (an agent's official mark on a
  neutral tile — Claude Code's Claude Spark, Codex's OpenAI Blossom with the
  word "Codex", a neutral glyph for anything else), the **status dot + word**,
  the **change preview** (a write grouped by agent and file, as plain words and
  a diff, through computing, nothing to change, applying, applied and failed
  partway), and the Coffer **Stroke C** logo as the sidebar mark and favicon. The
  reach control keeps its behaviour and vocabulary and takes the Foundations
  look, showing the chosen agents' badges.
- A Playwright visual baseline of every top-level route in light and dark,
  runnable locally and in CI, is the reference later page work is compared
  against.

## Capabilities

### Modified Capabilities

- `web-ui`: draws every colour from the theme tokens; follows the system theme
  with a per-viewer override; ships its fonts; shows an agent by its official
  mark; pairs every status colour with its word; previews a write before it
  lands; marks the app with the Coffer logo.

## Impact

- `frontend/src/index.css`, `frontend/tailwind.config.js`, `frontend/src/components/ui/*`,
  new shared components under `frontend/src/components/`, `frontend/src/lib/theme.ts`,
  the bundled font files under `frontend/src/assets/fonts/`, brand marks under
  `frontend/src/assets/brand/`.
- `scripts/check_frontend_colors.py` joins `make lint`.
- `e2e/`: a `visual` Playwright project with its own config and baselines.
- Docs: `.agents/visual-language.md`, `.agents/frontend.md`, and the docs site's
  design-system architecture page.
