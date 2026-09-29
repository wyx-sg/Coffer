## 1. Tokens and theme

- [x] 1.1 Foundations colour roles for light and dark in `src/index.css`, shadcn names as aliases; radius, type, weight, shadow, motion, z-index and size tokens in `tailwind.config.js`
- [x] 1.2 `src/lib/theme.ts`: System / Light / Dark preference in `localStorage coffer.theme`, resolved onto `<html data-theme>` before the first render and kept in step with the system
- [x] 1.3 Theme choice on Settings › General
- [x] 1.4 Colour gate `scripts/check_frontend_colors.py` in `make lint`, with its harness test; existing literals replaced by tokens
- [x] 1.5 Pages that used `accent` as the hover wash, the serif display face and raw literals moved onto roles

## 2. Fonts

- [x] 2.1 Figtree and JetBrains Mono woff2 (Latin, Latin Extended) with their OFL licences under `src/assets/fonts/`, declared in `index.css`

## 3. Components

- [x] 3.1 Base components in `src/components/ui` restyled to the Foundations spec
- [x] 3.2 Agent badge with the official marks (assets copied unchanged)
- [x] 3.3 Status dot + word
- [x] 3.4 Change preview with all six states
- [x] 3.5 Reach control on the Foundations look, with chosen agents' badges
- [x] 3.6 Coffer Stroke C mark as the sidebar brand and the favicon

## 4. Screenshot baseline

- [x] 4.1 `visual` Playwright config and spec: every top-level route × light / dark, fixed fonts, no animations, dynamic text masked
- [x] 4.2 Baselines recorded; `make verify-visual` / `make visual-update`

## 5. Docs

- [x] 5.1 `.agents/visual-language.md` and `.agents/frontend.md` rewritten for the token system and dark theme
- [x] 5.2 Docs site: design-system architecture page
