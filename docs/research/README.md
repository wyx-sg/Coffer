# Research Notes

One note per Coffer feature. Each surveys how **other** products and projects
implement that feature — mechanism, data model, UX, failure handling — so a
design can borrow from them or deliberately depart from them. A note is about
the outside world: Coffer appears only in its header, as links to the spec and
the ADRs the research informs. What Coffer decided, and why, lives in
[`docs/decisions/`](../decisions/README.md); what Coffer does lives in
`openspec/specs/`.

## Index

| Note | Feature | Coffer spec |
| --- | --- | --- |
| [MCP gateways](./mcp-gateways.md) | Aggregating many upstream MCP servers behind one endpoint: curation, tool overload, auth, isolation, tool-definition integrity | `mcp-gateway` |
| [Agent skills](./agent-skills.md) | Managing SKILL.md bundles once and delivering them into several agents | `skill-manager` |
| [Agent plugins](./agent-plugins.md) | Seeing and managing the plugins installed in a coding agent from outside it | `agent-registry` |
| [Agent transcript history](./agent-transcript-history.md) | Browsing and reusing the session transcripts agents store locally | `agent-registry` |
| [Provider switching](./provider-switching.md) | Switching the model provider, endpoint and key a coding agent uses | `provider-switching` |
| [Agent chat clients](./agent-chat-clients.md) | GUIs that drive locally installed agent CLIs as chat | `chat` |
| [IM agent bridges](./im-agent-bridges.md) | Driving a local coding agent from an IM app | `channels` |
| [Knowledge curation](./knowledge-curation.md) | Plain-Markdown knowledge bases co-maintained by people and an LLM | `knowledge` |
| [Agent memory](./agent-memory.md) | Capturing, consolidating and re-delivering what agents learn across sessions | `memory` |
| [Multi-machine sync](./multi-machine-sync.md) | Converging one user's vault across their machines through a remote they own | `vault-sync` |
| [Credentials & secrets](./credentials-secrets.md) | Holding secrets for agents and MCP servers without exposing plaintext | `credentials` |
| [Activity & audit](./activity-and-audit.md) | Audit logs, invocation logs, daemon logs, retention and the UI over them | `resource-framework`, `web-ui`, `daemon` |
| [Desktop shell & daemon](./desktop-shell-and-daemon.md) | A resident localhost daemon plus a native shell and CLI from one download | `daemon`, `desktop-app` |
| [Agent evaluation](./agent-evaluation.md) | Capturing interactions into datasets and gating CI on regressions | none — engineering harness |

Capabilities with no note: `resource-framework` (as a framework), `experimental-features`
and `internal-engine` — engineering internals where the ADRs carry the reasoning.

## How a note is written

- **One feature per note**, named after the feature, not after a product.
- **Mechanism over checkmarks.** Each product gets a section explaining how it
  works, concretely enough to reimplement the idea; a comparison table may
  summarise afterwards. Each note closes with *Patterns and trade-offs* and
  *Worth borrowing / worth avoiding*.
- **Choose products by adoption, not by familiarity.** Sort candidates by real
  use (GitHub stars, users) across the whole keyword space, and include the
  Chinese ecosystem by default — an earlier round of research, organised by
  category and by familiar names, missed the market leader in provider
  switching (cc-switch) and every Chinese IM bridge.
- **Primary sources, dated.** Vendor docs, repository files and release notes,
  linked inline; star counts and product status "as of" the research date.
- **No claims about Coffer's own state.** They rot faster than anything else in
  a note. A note is refreshed by re-researching the outside world, not by
  appending dated corrections: rewrite it in place and update its
  *Researched* date.
