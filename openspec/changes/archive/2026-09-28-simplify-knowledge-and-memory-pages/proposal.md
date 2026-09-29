# Simplify the knowledge and memory pages

## Why

The knowledge and memory pages ask the reader to manage things they cannot
meaningfully manage, and hide or split things they want to see:

- Every collection and every partition carries an Enabled / Disabled switch,
  but nobody turns a collection or a partition off: the whole layer is already
  switched by the experimental-features toggle, and a disabled partition is a
  file an agent can still open. The switch is a column and a header control
  with nothing behind them worth choosing.
- A collection's page can only read a document; changing one means leaving
  for an external editor. Skills already edit in place with a fingerprint
  guard, and knowledge is the layer people write in most.
- Material waiting in a collection's inbox is reported as a count ("71 new
  items are being merged") but cannot be looked at, so the reader cannot tell
  what is about to be merged.
- A partition's tree shows `.raw/`, the verbatim input to distillation, which
  is dozens of hash-named files that crowd out the notes and are not Coffer's
  answer to anything.
- Memory has two buttons for one intent: "Read agent memory" on the list
  (aggregation) and "Distil" on a partition (distillation). Either one alone
  leaves the notes stale.
- File trees and previews stop at 60% of the window height however large the
  window is, and a memory note's frontmatter renders as body text.

## What Changes

- **Knowledge and memory can no longer be disabled.** Every collection and
  every partition is served to every agent. The kinds declare themselves
  non-toggleable; the generic enable/disable route refuses them, a migration
  enables any row stored disabled, and the lists, detail headers and bulk bars
  drop the Status control.
- **Edit a knowledge document in place.** The preview gains the skill
  viewer's Edit / Save / Cancel with a fingerprint conflict check, backed by a
  new `PUT /api/v1/knowledge/file` that rewrites a document's body and keeps
  its frontmatter.
- **Show the inbox in the tree.** A collection's tree lists `.inbox/` as a
  folder whose items can be read (not edited); the pending-count banner and
  the filename filter above the tree are removed.
- **Hide `.raw/` from a partition's tree.** The tree and the read route stop
  offering it; the `derived` marker on tree nodes is removed with it.
- **One "Update memory" action.** `POST /api/v1/memory/sync` (and
  `coffer memory sync`) runs aggregation and then a distil pass over every
  partition that gained raw entries; the list page and the partition page
  share one button that calls it.
- **File panes fill the window.** Every file tree and preview extends to the
  bottom of the window and scrolls inside. A Markdown preview renders a file's
  frontmatter as metadata above the body rather than as body text.

## Capabilities

- `knowledge` — Serve every collection to every agent; show the inbox in the
  tree; edit documents in place; the page's shape.
- `memory` — Serve every partition to every agent; hide `.raw/` from the tree;
  one update action.
- `resource-framework` — A kind may declare it cannot be disabled.
- `web-ui` — The reach / status button is absent for a kind that cannot be
  disabled.
