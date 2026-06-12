# Coffer Docs Site (`docs-site/`) — Design

> **Status:** Approved design (brainstorm output) — pending implementation plan.
> **Date:** 2026-05-30
> **Scope:** A public, bilingual documentation portal for Coffer, deployed to
> GitHub Pages. Promotes the project _and_ hosts the full technical
> documentation (architecture, every spec, ADRs, engineering conventions).

This document captures the design agreed during brainstorming. It is the
contract for the implementation plan; if the plan or code disagrees with it,
update this document first.

The site lives under `docs-site/` (not `website/`, which would be ambiguous
with `frontend/` — the product's own web UI).

---

## 1. Goal & scope

Build a single site at `https://wyx-sg.github.io/Coffer/` that serves two
jobs at once:

1. **Promote & introduce** — a polished landing experience that explains what
   Coffer is and gets a developer to the repo / first install quickly.
2. **Be the project's documentation home** — architecture, **all** specs,
   **all** ADRs, the constitution / roadmap, and the engineering conventions,
   rendered on-site (not merely linked out), with sidebar navigation and
   full-text search.

The site is **fully bilingual** (English + 中文) with a language switcher,
matching the repository's existing bilingual convention.

**Non-goals** are listed in §9.

---

## 2. Audience & success criteria

**Primary audience:** developers who use AI coding agents (Claude Code, Codex)
and evaluate or adopt Coffer; contributors who need the architecture and specs.

A first-time visitor should, without scrolling far:

- understand Coffer in one sentence ("local-first MCP gateway / agent vault"),
- see the core value props,
- find the install command and a GitHub CTA,
- be one click from deep docs (guide, architecture, specs).

A contributor should be able to read any spec, ADR, or convention on-site, in
either language, and search across all of it.

---

## 3. Information architecture (sitemap)

English root `/` and Chinese `/zh/` share one structure. Top nav: **Guide /
Architecture / Reference / Contributing / GitHub**, plus the built-in language
switcher and search.

```
Home  (/  ·  /zh/)
  · Hero (Direction A — see §5)
  · Features grid (5 props)
  · How it works (data-flow diagram)
  · Quickstart teaser
  · Footer

Guide              (authored, bilingual)
  · Introduction (what / why)
  · Getting Started (install)
  · Register an MCP server
  · Connect a client (Claude Code / Codex)
  · Web UI
  · Desktop app
  · Concepts (resource kind · gateway · shim · local-first)

Architecture       (authored deep-dive, bilingual, Mermaid; ordered by
                    execution path, modelled on SQLite / Tailscale / MCP docs)
  · Principles (the problem · 3 principles · what Coffer is NOT · rejected alts)
  · System overview (anchor sentence + topology diagram + reading map)
  · Daemon & processes (detect-or-spawn + startup sequence diagram)
  · Resource framework (everything is a kind + lifecycle state diagram)
  · Layering & boundaries (import rules + importlinter)
  · Surfaces (REST · MCP · CLI · shim · Web · Desktop — uniform template)
  · Request lifecycle (end-to-end tool call + sequence diagram + error path)
  · Persistence (SQLite + table map + migrations)
  · Security (invariants: loopback · encrypted-credential-store · namespacing)
  · Audit & accountability (audit log · invocation log · retention)
  · Observability (structured logging · trace correlation · error model)
  · Distribution (PyInstaller + Tauri sidecar)

Reference          (synced from the repo at build time — see §4; an authored
                    landing page + an auto-generated grouped, collapsible
                    sidebar — see §6)
  · Specs: every folder under specs/ — currently 001 MCP Gateway · 002 UI
           Shell · 003 Desktop (whichever of spec / plan / data-model /
           quickstart / research each folder has); future specs appear
           automatically as they merge to main
  · ADRs: every ADR under docs/decisions/ (currently ADR-001 … ADR-008) + index
  · Project memory: Constitution · Roadmap · Architecture (canonical)
  · Engineering conventions (agents/*)

Contributing       (authored, bilingual)
  · Contributing guide · Conventional Commits · SDD workflow · Security
```

---

## 4. Content strategy

Content is split into two layers with different sourcing rules.

### 4.1 Receptor layer — authored, bilingual

The Home, Guide, Architecture overview, and Contributing pages are **written
fresh for the site**, in both English and 中文. They draw on the README and
architecture notes but are tuned for a first-time reader. These are the only
pages we hand-maintain in both languages.

### 4.2 Reference layer — synced from canonical, bilingual

The full specs, ADRs, project-memory docs, and engineering conventions are
**already canonical Markdown in the repo, and already bilingual** via the
existing `.zh.md` convention (verified: `.specify/memory/*`, all ADRs,
`agents/*`, and `specs/001–003` ship `.zh.md` siblings).

A build-time sync script copies them into the site so there is **one source of
truth and zero drift** (honoring the constitution's Spec-as-Truth principle):

- `foo.md` → `docs-site/reference/<area>/foo.md` (English tree)
- `foo.zh.md` → `docs-site/zh/reference/<area>/foo.md` (Chinese tree, `.zh` stripped)
- Repo-relative links (e.g. `../../docs/decisions/ADR-002…`) are rewritten to
  on-site routes.
- **`tasks.md` is excluded** — it is a transient implementation tracker, not
  reference documentation. (This also closes the one translation gap:
  `specs/001-mcp-gateway/tasks.md` has no `.zh.md`.)
- Source areas: `specs/`, `docs/decisions/`, `.specify/memory/`, `agents/`.
- Generated `reference/` and `zh/reference/` trees are **git-ignored**; they are
  regenerated on every build.

**Translation policy:** the receptor layer is authored bilingual; the reference
layer's Chinese comes from the repo's `.zh.md` files. If a future canonical
doc lacks a `.zh.md`, the sync falls back to the English file for the Chinese
route and the build logs a warning (so the gap is visible, never silent).

---

## 5. Visual language

Reuse the **"Coffer warm"** visual language from spec 002
(`frontend/src/index.css`, `agents/ui-shell/visual-language.md`) so the site
matches the product:

- **Palette:** cream paper background `#FAF9F5`, near-black ink `#1F1B17`, clay
  accent `#C96442` (used sparingly — primary CTA, active nav, links), warm
  beige `#F0EBE0` fills, warm-grey muted text `#6B645A`, border `#E8E4DA`.
  Status hues: green `#5B7C5C`, amber `#B07A2D`, clay-red `#A14D3F`.
- **Typography:** Source Serif for headings (serif, `tracking-tight`), Inter /
  system sans for body, SFMono / Menlo for code & identifiers.
- **Light-only** (no dark mode — matches spec 002's deliberate choice);
  enforced via VitePress `appearance: false`, so no (non-functional) theme
  toggle is rendered.
- Calm, considered, Claude.ai-adjacent feel.

These override VitePress's default (cool/blue) theme via its CSS custom
properties (`--vp-c-brand-*`, `--vp-c-bg`, fonts, etc.) in a theme stylesheet.

**Home page — Direction A (chosen):** an editorial, restrained hero — a large
centered serif headline, a short subtitle, one clay primary CTA + a ghost
secondary, and a single inline install command. Below the hero the page
continues: **Features grid → How it works (the client → shim → daemon →
upstream data-flow diagram) → Quickstart teaser → footer.** (Direction A sets
the hero tone; the data-flow diagram from the rejected "Direction B" is kept,
lower on the page.)

---

## 6. Technical approach

**Framework: VitePress.** Chosen because it is Vite-based (matching the
existing `frontend/` build chain), ships built-in i18n with a language
switcher, built-in local search, a home/hero layout, and is the most flexible
about Markdown source location — letting us render the existing specs with
minimal massaging. Deploys to GitHub Pages with a single Action.

**Repo layout** — a self-contained project under `docs-site/`:

```
docs-site/
  package.json                 # vitepress + vitepress-plugin-mermaid (own deps)
  .vitepress/
    config.mts                 # i18n locales, path-scoped nav/sidebar, theme, search, mermaid
    theme/                      # Coffer-warm CSS overrides
    reference-sidebar.json      (generated, git-ignored)  # grouped reference sidebar
  index.md   zh/index.md       # bilingual home (hero + features + how-it-works…)
  reference.md  zh/reference.md # authored Reference landing (category overview)
  guide/…    zh/guide/…         # receptor layer (authored, bilingual)
  architecture/…  zh/architecture/…   # 12-page deep-dive (authored, bilingual)
  contributing/…  zh/contributing/…
  reference/        (generated, git-ignored)   # English specs/ADRs/…
  zh/reference/     (generated, git-ignored)   # Chinese .zh.md → .md
  scripts/sync-reference.mjs   # build-time sync + emits reference-sidebar.json (§4.2)
```

**Key config:**

- i18n: root locale = English (`/`), `zh` locale = `/zh/`; per-locale nav &
  sidebar.
- `base: '/Coffer/'` (GitHub Pages project site). If a custom domain is added
  later, switch to `base: '/'` and add a `CNAME`.
- Search: `themeConfig.search.provider = 'local'` (i18n-aware, no external
  service — consistent with the project's no-vendor-lock-in posture).
- Mermaid via `vitepress-plugin-mermaid` for architecture diagrams.
- **Light-only** via `appearance: false`.
- **Sidebars are path-scoped** per section (`/guide/`, `/architecture/`,
  `/reference`, `/contributing/`). The **reference sidebar is auto-generated**
  by the sync script (`reference-sidebar.json`) from the synced tree — grouped
  (Specs → per-spec collapsible · ADRs · Project memory · Conventions) with
  labels taken from each file's H1 — so it scales as specs/ADRs are added.
- Node 22; deps isolated from `frontend/` so the app bundle is untouched.

---

## 7. Build & deploy

**Build:** `npm run build` in `docs-site/` runs the sync script as a `prebuild`
step, then `vitepress build` → static output in `docs-site/.vitepress/dist`. A
`predev` hook runs the same sync for local `vitepress dev`.

**Deploy:** `.github/workflows/pages.yml`

- **Triggers:** push to `main` touching `docs-site/**` or any synced source dir
  (`specs/**`, `docs/decisions/**`, `.specify/memory/**`, `agents/**`); plus
  `workflow_dispatch`.
- **Build job:** checkout → `actions/setup-node@v4` (Node 20, cache npm) →
  `npm ci` → `npm run build` → `actions/upload-pages-artifact` (the `dist`).
- **Deploy job:** `actions/deploy-pages` with `permissions: pages: write,
id-token: write` and a `concurrency` group so overlapping runs don't race.
- **PR check:** a build-only job (no deploy) on PRs touching `docs-site/**` so a
  broken site fails CI before merge.
- **One-time manual setup:** repo **Settings → Pages → Source = "GitHub
  Actions"** (cannot be enabled from code; called out for whoever merges).

---

## 8. Alignment with the constitution & invariants

- **Languages.** VitePress is a TypeScript/Node toolchain — within the
  constitution's "TypeScript 5.x for frontend" allowance; no new primary
  language is introduced.
- **Local-first (NON-NEGOTIABLE).** The site is public, static, build-time
  content; it stores and touches **no vault state**, so the local-first
  invariant is unaffected. Search is local/in-bundle (no external search
  service).
- **Spec-as-Truth.** The reference layer renders the canonical repo Markdown
  via build-time sync — no duplicated, drift-prone copies.
- **Open-source-readiness.** MIT project; the site surfaces the license,
  contributing flow, and security policy.

---

## 9. Out of scope / non-goals

- **Dark mode** — light-only, matching spec 002.
- **Versioned docs** — single "latest" only; revisit if releases diverge.
- **Blog / changelog feed** — not now.
- **Custom domain** — ship on the `github.io/Coffer/` path; domain is a later,
  config-only change.
- **Translating `tasks.md` or other transient trackers** — excluded from the
  site entirely.
- **Auto/machine translation** — unnecessary; the repo is already bilingual.

---

## 10. Open questions / future

- Logo / favicon / social-share (OG) image — does Coffer have a mark, or do we
  derive a simple serif wordmark + clay dot from the visual language?
- Whether to later add the `docs-site/` build to the repo's existing `make
verify` aggregate, or keep it solely in `pages.yml` + the PR check.
- A `docs-site/DESIGN.zh.md` translation of this design doc, if a Chinese
  canonical is wanted.
