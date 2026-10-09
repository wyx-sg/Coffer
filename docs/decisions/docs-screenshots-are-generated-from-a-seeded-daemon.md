# Docs Screenshots Are Generated From a Seeded Daemon, Not Captured by Hand

**Status**: Accepted
**Date**: 2026-10-09
**Deciders**: Yuxing Wu (project owner)
**Related**: [Visual baseline](../../.agents/testing.md), research note [Documentation screenshots](../research/docs-screenshots.md), [The Desktop Shell Hosts the Shared Frontend](desktop-shell-over-a-shared-frontend.md)

## Context

The docs site had one picture of the app, `docs-site/public/overview.png`,
shown on both the English and the Chinese home page. It was captured by hand,
is English-only, and had already drifted from the sidebar. The Get started and
Guides pages, which tell the reader "open Agents, then press Connect", had no
pictures at all. The owner wants the home page to show the product as a set of
tabs, one screenshot per tab, and wants the guides to carry pictures where a
reader has to find something on screen.

Forces on the answer:

- **The UI changes weekly.** Of everything the docs hold, a screenshot is the
  one thing that goes stale silently: nothing fails when a button is renamed.
- **Two languages, two themes.** Every picture would otherwise be four captures
  that someone has to keep level.
- **The docs site is Vue (VitePress); the app is React.** Components cannot be
  shared between them, and the frontend has no mode that runs without a daemon.
- **A pipeline already exists.** `e2e/visual` drives the real frontend against a
  real daemon with a fixed HOME, fixed ports and frozen animation, in light and
  dark, and has measured zero differing pixels across runs.
- **The home page picture needs a lived-in app,** not a fresh install: servers
  with problems, skills, memory. A fresh daemon shows empty states.

## Options Considered

### Option A — A second Playwright project that seeds a real daemon and writes docs images (chosen)

A `docs` Playwright config beside the visual one starts its own daemon, creates
a fixed set of demo resources through the daemon's own REST API, opens each
documented page at 2x pixel density in English and Chinese, light and dark, and
writes PNGs into `docs-site/public/shots/<lang>/<theme>/<name>.png`. The images
are committed; the docs build needs no daemon. Each shot is one named scenario,
and pages refer to it by name.

- Good: the picture is the real UI, so it is exactly what the reader will see.
  Re-running after a UI change refreshes every image, in both languages.
- Good: reuses the daemon start script, the freeze CSS and the settle checks of
  the visual suite, so there is one place that knows how to make the app hold
  still.
- Good: seeding through the REST API exercises the same routes the UI uses, so
  the scenario breaks loudly, not silently, when a route changes.
- Cost: a scenario per picture, and flaky scenarios need the same care the
  visual suite already gives its own. A page that is not worth a scenario does
  not get a picture.
- Cost: committed binaries grow the repository; mitigated by capturing only
  the region a step needs and by keeping the set small.

### Option B — Hand-captured screenshots with a style guide

Anyone captures a window on their Mac and drops the file in `public/`, following
a rule sheet (GitHub Docs works this way: crop to the element, light theme,
placeholder account, 144 dpi, 250 KB cap).

- Good: nothing to build; a person judges every crop.
- Bad: it goes stale without a signal, which is the failure we already have.
  Two languages and two themes multiply the manual work, so in practice only
  English light ever gets updated.
- Lost because the current state, a picture that contradicts the sidebar, is the
  outcome of this option.

### Option C — Reuse the visual-baseline images as the docs images

Point the docs at `e2e/visual/specs/__screenshots__`.

- Good: no new capture step.
- Bad: those images are of a fresh daemon on purpose, with clock text and
  per-run values masked; they are 1280x800 at 1x, per platform, and show empty
  states. They are a regression oracle, and bending them toward marketing would
  weaken the oracle.
- Lost because a test baseline and a published picture have opposite needs.

### Option D — Embed the live app in the docs (iframe or a replica)

Build the frontend as a static demo bundle with a mock API layer and embed it, so
the home page tabs are clickable and crisp at any zoom, as HTML-capture demo
tools do.

- Good: the most convincing result, and it follows the UI automatically.
- Bad: the frontend has no daemon-less mode, so this needs a mock API covering
  every page shown, kept in step with the wire contract, plus a second build of
  the frontend shipped with the docs and its weight on first load.
- Evaluated 2026-10-09 against [onorca.dev](https://www.onorca.dev/): its hero
  is not an iframe or a replay of the real app but a hand-built HTML and CSS
  mock-up of the window, and its feature grid is static posters. A mock-up like
  that is crisp and cheap to load but is a second copy of the UI that drifts the
  way a hand-captured picture does, so it fails this ADR's first force.
- Deferred, not rejected: the version that fits is a read-only replay. The
  seeded daemon's responses are recorded once per scenario and served to a
  static build of the real frontend inside an iframe on the home page only, so
  the fixture comes from Option A's seed and the UI is the real one. Clicks
  that write have nothing to answer them, which is the limit of this version.
  It is worth building when the home page needs hover and click inside the
  window, not before.

## Decision

Docs images are generated by a Playwright `docs` project from a seeded real
daemon (Option A), committed under `docs-site/public/shots/`, and referenced
from pages and from the home page tabs by name. English and Chinese, light and
dark, come from one scenario. Nobody edits these files by hand: a changed image
is a changed scenario or a changed UI, regenerated with `make docs-shots`.

## Consequences

- A UI change that moves something a guide points at is fixed by re-running one
  command and reviewing the image diff, not by remembering which page showed it.
- The seeded data is shared fixture material: the demo agents, servers and
  skills are named once, so every picture tells one consistent story.
- The set of scenarios is a deliberate list, so a new guide asks "does a reader
  need to find this on screen?" before adding one.
- Option D stays open and reuses the seed.
- Pictures show the desktop app, not a browser tab: the scenario stands in for
  the Tauri host (a Mac platform, the daemon handshake, a screen larger than the
  window) so the app draws its own title strip, and the three traffic lights the
  system would draw are painted on top. Full-window shots keep that chrome;
  page-level shots crop to the page below it.
