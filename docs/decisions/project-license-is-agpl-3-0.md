# Coffer Is Licensed Under AGPL-3.0-or-later

**Status**: Accepted
**Date**: 2026-10-05
**Deciders**: Asen (project owner)
**Related**: [principles §III Open-Source-Readiness](../../docs-site/architecture/principles.md), [`seatalk-websocket-inbound`](seatalk-websocket-inbound.md), [`channel-adapter-framework`](channel-adapter-framework.md)

## Context

Coffer shipped under MIT from v0.0.1. MIT lets anyone take the code, close it
and ship it, or run it as a service, giving nothing back. The owner does not
want the work taken private that way: whoever builds on Coffer must release
what they build under the same terms, with its source.

The forces:

- **Coffer is a daemon with a web UI.** The easiest closed reuse is not
  redistribution but hosting: a "team Coffer" offered over the network, which
  never hands anyone a copy. A licence that only binds distribution misses it.
- **Every dependency is permissive** (FastAPI, uvicorn, React, Radix, TanStack,
  Tauri, CodeMirror: MIT, BSD or Apache-2.0), all of which may be combined into
  an AGPL-3.0 work, so no dependency blocks the choice.
- **Distribution is a signed `.dmg` and a CLI archive**, not the Mac App Store,
  whose terms conflict with the GPL family.
- **One human author.** The git history has a single human contributor, so
  relicensing needs no one else's consent. Releases already made under MIT stay
  available under MIT.
- **What comparable tools do.** A survey on 2026-10-05 of 27 MCP gateways,
  agent managers and local AI tools found 10 on MIT, 9 on Apache-2.0, 1 on
  MPL-2.0, 3 on GPL/AGPL (Basic Memory and claudecodeui among them), and 5 on
  open-core or source-available terms. Four projects (MetaMCP, Jan, claude-mem,
  Zed's last AGPL crate) moved off AGPL between 2025 and 2026 to widen adoption,
  which is the cost this choice accepts.

## Options Considered

### Option A — AGPL-3.0-or-later (chosen)

Strong copyleft: a distributed derivative must be AGPL-3.0 with its complete
source (§4–6), and §13 extends that to anyone who lets users interact with a
modified version over a network. Copyright notices must be kept, and an
interactive UI that shows them must keep showing them (§5(d)). "Or later" lets
the work follow a future FSF revision, as the FSF recommends.

Pros: closes both closed redistribution and the hosted-service gap; a standard,
OSI-approved licence. Cons: some companies forbid AGPL code outright, which
costs users and contributors; it does not forbid commercial use, only closed
use. Wins because it is the one standard licence that covers the hosting case.

### Option B — GPL-3.0-or-later

The same copyleft without §13. Loses because a hosted, modified Coffer would
owe no one its source, which is the reuse most likely for a daemon with a web UI.

### Option C — MPL-2.0

File-level copyleft: changes to Coffer's files must be published, new files
need not be. Loses because a closed product can wrap Coffer with its own
proprietary files.

### Option D — Stay permissive (MIT, or Apache-2.0 with a `NOTICE`)

Pros: widest adoption; Apache-2.0 adds a patent grant and a carried
attribution notice. Cons: either lets the code be taken closed. Loses on the
requirement itself.

### Option E — A source-available licence (BSL, Elastic, a custom licence)

Pros: can forbid commercial competition outright. Cons: not open source, which
principle §III commits Coffer to; a custom licence must be maintained and read
clause by clause by every reviewer. Loses because forbidding commercial use is
not the goal.

## Decision

Coffer is licensed under the GNU Affero General Public License, version 3 or
(at your option) any later version. `LICENSE` holds the unmodified licence text,
the READMEs carry the copyright line, and every manifest declares
`AGPL-3.0-or-later`. Contributions are accepted under the same licence.

## Consequences

- The licence is named in `LICENSE`, both READMEs, `AGENTS.md`,
  `CONTRIBUTING.md`, the docs site (footer, contributing, FAQ, principles),
  `backend/pyproject.toml`, `desktop/Cargo.toml`, `openspec/config.yaml` and
  the About page in Settings; a future change of licence updates all of them.
- A new dependency must be AGPL-3.0-compatible: GPL-2.0-only and
  source-available code cannot be added.
- The rule that Coffer cannot vendor or declare an unlicensed dependency
  ([`seatalk-websocket-inbound`](seatalk-websocket-inbound.md)) is unchanged.
- Code contributed by others is theirs under AGPL; relicensing it later (for a
  commercial licence, or back to permissive) needs their consent unless a
  contributor agreement is adopted first.
- Releases published before this change were under MIT and remain available
  under MIT.
