## Why

Notes and knowledge pages written by agents often carry a ```` ```mermaid ````
block — a flowchart, a sequence of calls, a state machine. Every Markdown
preview in Coffer showed it as code, so the reader had to picture the diagram
from its source. The options are argued in ADR
`markdown-diagrams-render-with-mermaid`.

## What Changes

- Every Markdown preview (Knowledge, a skill's files, Memory, an agent's files,
  conversation and channel text in the app) draws a ```` ```mermaid ```` block
  as its diagram, every type Mermaid draws, in the app's light or dark palette.
- Mermaid loads only when a diagram is on the page, never in the main bundle,
  and runs with `securityLevel: "strict"`, so a diagram never runs code.
- A block that cannot be drawn stays the code block it was written as, with one
  line saying it could not be drawn.

## Impact

- `frontend/src/components/Markdown.tsx`, new `MermaidDiagram.tsx`,
  `lib/theme.ts` (`useResolvedTheme`); dependency `mermaid`.
- Spec `web-ui`: new requirement "Draw Mermaid diagrams in every Markdown preview".
- docs-site guides `web-ui.md`, `knowledge.md` (en, zh); design canvases
  Foundations (Markdown preview) and Context (Knowledge reader).
