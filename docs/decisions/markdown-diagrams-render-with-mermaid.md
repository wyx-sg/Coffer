# Markdown Diagrams Render With Mermaid, in the Browser, Loaded on Demand

**Status**: Accepted
**Date**: 2026-11-11
**Deciders**: Yuxing Wu
**Related**: [Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md); [The Desktop Shell Hosts the Shared Frontend and Owns Only What a Browser Cannot Do](desktop-shell-over-a-shared-frontend.md); spec web-ui "Draw Mermaid diagrams in every Markdown preview"; OpenSpec change `draw-mermaid-diagrams-in-markdown`

## Context

Agents write diagrams as text. A knowledge page explaining a flow, a skill's
notes on a protocol, a reply describing a state machine: each comes with a
fenced ```` ```mermaid ```` block, because that is the diagram format agents
are trained on and the one GitHub draws. Coffer has one Markdown renderer
(`frontend/src/components/Markdown.tsx`, react-markdown) behind every preview:
Knowledge, a skill's files, Memory, an agent's files, and conversation and
channel text in the app. It showed such a block as code, so the reader had to
picture the diagram from its source.

The forces:

- **Local-first and private.** Coffer's principles keep a person's data on
  their machines. A diagram in a knowledge page is that data; it must not be
  sent anywhere to be drawn.
- **A document never runs code.** The renderer already sanitises a document's
  own HTML for this reason. A diagram is drawn from text someone else (an
  agent, an import) wrote.
- **The app stays light.** The main bundle is already about 1.8 MB; most pages
  never show a diagram.
- **Lean.** No setting, no per-collection switch, no diagram format of Coffer's
  own; what the person writes in their own editor should look the same here.

## How comparable products handle it

- **GitHub** draws ```` ```mermaid ```` (and `geojson`, `topojson`, `stl`, and
  `$…$` math) in Markdown files, issues and comments. Mermaid runs client-side
  in a sandboxed iframe; a failure shows an error box with the source.
- **GitLab** draws Mermaid client-side, and PlantUML or other formats only
  when an admin points it at a PlantUML or Kroki server.
- **Obsidian**, **Typora**, **Joplin** and **Notion** draw Mermaid code
  blocks client-side, built in, with no setting. Obsidian shows Mermaid's own
  error text in place of a broken diagram.
- **VS Code's** built-in Markdown preview draws none; an extension adds
  Mermaid.

Mermaid fenced blocks are the common ground; anything beyond them needs a
server or a plugin.

## Options Considered

### Option A — Mermaid in the browser, loaded on demand, strict (chosen)

The shared renderer hands every ```` ```mermaid ```` block to a
`MermaidDiagram` component. The first such block on a page imports Mermaid
(its own chunk, about 165 kB gzipped plus per-diagram chunks), initialises it
with `securityLevel: "strict"` and the app's light or dark theme, parses the
block, and inserts the SVG Mermaid returns. Until then, and for good when
parsing or drawing fails, the block shows as the code block it is, with one
line saying it could not be drawn.

- **Pros**: nothing leaves the machine; every diagram type Mermaid draws
  (flowchart, sequence, state, class, ER, Gantt, pie, mindmap, timeline, and
  the rest) works with no list of Coffer's own; it matches GitHub and
  Obsidian, so a file reads the same in the person's editor; one change in one
  renderer reaches every preview; the main bundle is unchanged.
- **Cons**: a dependency of about 110 packages in the lock file; the first
  diagram on a page waits for the chunk (local, so tens of milliseconds);
  strict mode drops Mermaid's `click` callbacks and HTML labels.
- **Why it wins**: it is the only option that is private, draws what agents
  write, and costs nothing until used.

### Option B — Keep showing the source

- **Pros**: no dependency, nothing to secure.
- **Cons**: the reader reconstructs a diagram in their head; the gap with
  GitHub and Obsidian stays visible for the files people read most.
- **Loses because** the person asked to see diagrams, and Option A costs the
  main bundle nothing.

### Option C — A rendering service (Kroki, mermaid.ink, a PlantUML server)

Send the block's text to a server that returns an image.

- **Pros**: one integration covers Mermaid, PlantUML, Graphviz and more; no
  library in the app.
- **Cons**: every diagram's text leaves the machine, against the local-first
  principle; it fails offline; a self-hosted server is a second program for a
  single-user tool to run.
- **Loses on privacy.** The Confluence import already refuses to send a
  diagram to a rendering service (spec knowledge "Import a Confluence page as
  a readable source with its attachments") for the same reason.

### Option D — Draw on write, keep SVG files in the vault

When a file with a Mermaid block is written, Coffer (or the agent) renders an
SVG beside it and the preview shows the image.

- **Pros**: the preview needs no library; other tools see the picture too.
- **Cons**: a second file per diagram that drifts from its source, synced to
  every Mac; drawing needs a headless browser on the writing side; a file
  edited in the person's own editor has no picture until something re-renders
  it.
- **Loses because** it adds files and machinery Coffer must keep consistent,
  where Option A derives the picture at read time.

### Option E — Mermaid plus more formats (PlantUML via a server, Graphviz via WebAssembly, math via KaTeX)

- **Pros**: covers what some pages hold.
- **Cons**: PlantUML needs a server (Option C's problem); Graphviz's WASM build
  is about 1.5 MB; each is another dependency for blocks Coffer's files rarely
  hold.
- **Loses for now**: lean scope. Math (KaTeX, the one GitHub also draws) is the
  candidate if pages start to need it; it would be a second rehype plugin in
  the same renderer, decided in its own ADR.

### Option F — Mermaid's `sandbox` security level (an iframe per diagram, as GitHub does)

- **Pros**: the strongest isolation.
- **Cons**: each diagram is an iframe sized by guesswork, which clips or leaves
  gaps; the find bar cannot reach inside it; it does not follow the app's
  theme without messaging.
- **Loses because** `strict` already sanitises the SVG with DOMPurify and turns
  off scripts, click handlers and HTML labels, and the desktop shell's
  Content-Security-Policy allows no inline script (`script-src 'self'`), so the
  extra isolation buys little here.

## Decision

Every Markdown preview draws ```` ```mermaid ```` fenced blocks with Mermaid in
the browser. Mermaid is imported only when a page holds such a block, runs at
`securityLevel: "strict"`, and follows the app's resolved theme (Mermaid's
greyscale `neutral` theme in light, `dark` in dark, the closest to the app's
own surfaces). A block that
cannot be drawn shows its source and one line saying so. No other diagram
format is drawn, and nothing is sent anywhere to draw one.

Rules for later changes: keep Mermaid out of the main bundle (dynamic import
only); never lower the security level; a new diagram format is a new ADR.

## Consequences

- One renderer change reaches Knowledge, skills, Memory, agent files, and
  conversation and channel text in the app. Channel messages sent to SeaTalk
  or Telegram are unchanged: those apps show the source.
- `frontend/src/components/MermaidDiagram.tsx` owns loading, the theme and the
  fallback; `Markdown.tsx` only routes ```` ```mermaid ```` blocks to it.
- Mermaid updates arrive as ordinary dependency bumps; a diagram type added
  upstream appears without a Coffer change.
