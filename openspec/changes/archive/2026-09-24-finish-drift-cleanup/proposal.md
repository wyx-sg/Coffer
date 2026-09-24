## Why

The knowledge pass that rewrites a collection unattended is called curation in
the code, the settings and the UI, but two vault-sync requirement titles still
call it "tidy", so every citation of them quotes the old name. Code, tests and
e2e headers also still carry task and review-finding ids (`T-0xx`, `TEST-0xx`,
`P1-1`) from planning documents that no longer exist, and the
requirement-citation gate reads only one spelling of a citation. The harness ADR still reads "Proposed" although most of it
shipped.

## What Changes

- vault-sync: "Never overlap a tidy pass and a round" becomes "Never overlap a
  curation pass and a round" and "Let an edit beat a tidy deletion" becomes
  "Let an edit beat a curation deletion". Every citation follows.
- Task and review-finding ids in code comments, docstrings, tests and e2e
  headers are replaced by the requirement title they guard, or dropped.
- `scripts/check_spec_citations.py` treats `T-<digits>`, `TEST-<digits>` and
  `P<n>-<n>` as retired id forms; it recognises a citation whose capability is
  followed by a colon or wrapped in backticks or bold; and a quote that closes
  a string literal or opens something other than a letter is not read as a
  title.
- The ADR "Industrial-Grade Harness, Built in Layers" is Accepted, with a note
  naming what shipped and what was not built; the ADR index follows.

## Capabilities

### New Capabilities

### Modified Capabilities

- `vault-sync`

## Impact

Comment and docstring text across the MCP gateway, daemon CLI, sync and
knowledge curation modules and their tests; the citation gate and its tests; `docs/decisions/industrial-grade-harness-in-layers.md` and
`docs/decisions/README.md`.
