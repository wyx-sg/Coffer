# Architecture Decision Records (ADR)

Coffer records every major technical or architectural decision as an
ADR. ADRs capture **why** — code shows _what_, this directory shows
_why we chose what we chose_.

## When to write an ADR

Write one for any **technical** decision that meets at least one of these:

- Hard to change later without breaking compatibility or rewriting large areas.
- Affects more than one module, or imposes structural constraints on future work.
- Has non-obvious trade-offs that future engineers (or future you) will question.
- Diverges from a default, a popular convention, or a project rule
  (a clause of the [principles](../../docs-site/architecture/principles.md), a prior ADR).

Do **not** write an ADR for:

- Library version bumps that don't change API surface.
- Routine bug fixes.
- Product scope — what a capability does and does not do belongs in its spec's
  `## Purpose` or in the requirement that bounds it.
- Project process — how we branch, review or release belongs in `.agents/`.
- Naming or formatting preferences, and UI conventions (`.agents/frontend.md`).
- A survey of how other products solve a problem — that is a research note
  under [`docs/research/`](../research/README.md), which an ADR may cite.

## One technical point, every option argued

- **One decision per file.** If the Decision section needs "and also", it is two
  ADRs. A decision that only makes sense beside another links to it rather than
  absorbing it.
- **Every serious option is written out**, the chosen one included: how it
  would work, what it is good at, what it costs, and the concrete reason it won
  or lost. "Considered and rejected" with no reason is not an option. A reader
  who disagrees with the choice should find their preferred option already
  there, argued on its merits.
- **Evidence over assertion.** Where a choice rests on a measurement, a platform
  limit or an incident, name it (the number, the API doc, the PR).
- **Length follows the decision.** There is no line limit; there is a
  one-decision limit. Implementation detail that does not bear on the choice
  belongs in the code, the spec, or the architecture docs.

## File naming and lifecycle

- Filename: `short-kebab-case-title.md` — the title, in kebab case, with no
  number. Numbers were dropped because deleting an ADR left a hole in the
  sequence, and compacting those holes would have made every surviving
  reference to a retired number point silently at an unrelated live decision —
  which had already happened once. A name cannot do that, and chronology is
  carried by each ADR's own `Date`.
- This directory records the **live** design, not a chronological archive. A
  reader must be able to learn today's answer by reading the ADRs present, never
  by replaying a chain of supersessions. So:
  - When a decision changes, **rewrite the ADR that owns it** so it reads as if
    written today. The design it replaced becomes one of its options, argued
    like any other — not an `Amended` note, a struck-through line or a revision
    log.
  - When the thing an ADR decided is **removed outright**, delete the ADR.
  - Keep an ADR marked `Superseded by <title>` only when the superseded design
    still explains a constraint the live one inherits.
  Git history is the archive: `git log --follow docs/decisions/` recovers any
  decision this directory no longer states.

## Status values

| Status                  | Meaning                                             |
| ----------------------- | --------------------------------------------------- |
| `Proposed`              | Drafted, not yet adopted.                           |
| `Accepted`              | In effect.                                          |
| `Superseded by <title>` | No longer the live answer; link to its replacement. |
| `Deprecated`            | Withdrawn without replacement (rare).               |

## Template

```markdown
# <short title in title case — states the decision>

**Status**: Proposed | Accepted | Superseded by [<title>](<file>.md)
**Date**: YYYY-MM-DD (when the decision in its current form was taken)
**Deciders**: <names / roles>
**Related**: [<ADR title>](<file>.md), spec <capability>, research note, PR

## Context

<The problem and the forces on it: constraints, measurements, incidents,
the principles clause or neighbouring ADR it has to live with. Enough that a
reader could weigh the options below without having been there.>

## Options Considered

### Option A — <name> (chosen)

<How it works. Pros. Cons. Why it wins.>

### Option B — <name>

<How it works. Pros. Cons. The concrete reason it loses.>

<…every serious option, including the design this one replaced.>

## Decision

<The choice, stated as today's design in a few sentences, plus the rules it
implies that a future change must respect.>

## Consequences

<What becomes easier, what becomes harder, what obligations follow, and where
in the code or spec the decision is enforced.>
```

## Index

Grouped by area. Every ADR here is `Accepted` and states the live design.


### Resource framework & persistence

| ADR | Decision |
| --- | --- |
| [`resource-framework-upfront`](resource-framework-upfront.md) | The Resource Framework Is Core Domain, Designed Before the Second Kind |
| [`command-line-parity-with-the-web-ui`](command-line-parity-with-the-web-ui.md) | Every Web UI and Desktop Operation Has a `coffer` Command Over the Same Route |
| [`kind-plugin-contract`](kind-plugin-contract.md) | A Kind Plugs In as One Frozen Record of Optional Hooks: Validators Before the Write, Reactions After |
| [`identity-is-the-uid-inside-the-file`](identity-is-the-uid-inside-the-file.md) | A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label |
| [`names-visible-to-agents-are-fixed`](names-visible-to-agents-are-fixed.md) | Names Visible to Agents Are Fixed |
| [`provider-and-channel-names-are-free-text`](provider-and-channel-names-are-free-text.md) | A Provider's and a Channel's Name Is Free Text, and Their Files Are Named by uid |
| [`per-agent-resource-scope`](per-agent-resource-scope.md) | Per-Agent Resource Scope Is One Framework Allow-List, Enforced by Each Kind |
| [`reach-is-machine-local-stored-by-uid-never-synced`](reach-is-machine-local-stored-by-uid-never-synced.md) | Reach Is Machine-Local: Stored by uid in `local/reach.json`, Never Synced |
| [`code-layout-layer-first`](code-layout-layer-first.md) | Code Layout Is Layer-First, With One Subdirectory per Kind |
| [`composition-root-explicit-wiring`](composition-root-explicit-wiring.md) | Kinds Are Wired Explicitly by One Composition Root, With No Global Registry |
| [`storage-is-five-classes-by-nature`](storage-is-five-classes-by-nature.md) | Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy |
| [`history-is-one-sqlite-file-written-only-by-the-daemon`](history-is-one-sqlite-file-written-only-by-the-daemon.md) | History Is One SQLite File, `runs.db`, Written Only by the Daemon and Migrated Forward at Startup Through One Alembic Lineage |
| [`every-vault-file-carries-its-format-version`](every-vault-file-carries-its-format-version.md) | Every Vault File Carries Its Own Format Version; One Owner Machine Commits Layout Upgrades |
| [`every-vault-write-is-a-validated-commit-naming-its-writer`](every-vault-write-is-a-validated-commit-naming-its-writer.md) | Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer |
| [`audit-and-retention`](audit-and-retention.md) | Audit Every Change With Its Actor, Log Every Invocation, Prune Per Table |
| [`secret-uses-are-read-apart-from-changes`](secret-uses-are-read-apart-from-changes.md) | Secret Uses Are Read Apart From Changes |
| [`runs-db-gives-pruned-space-back`](runs-db-gives-pruned-space-back.md) | `runs.db` Gives Pruned Space Back With a Threshold `VACUUM`, and Copies Itself With `VACUUM INTO` |
| [`one-level-triggered-reconciler-compares-parameters`](one-level-triggered-reconciler-compares-parameters.md) | One Level-Triggered Reconciler Converges What Coffer Writes Outside Its Database, Comparing Parameters |
| [`wire-contract-generated-from-the-pydantic-models`](wire-contract-generated-from-the-pydantic-models.md) | The Wire Contract Is Generated From the Pydantic Models, and the Frontend Client From the Contract |
| [`background-work-runs-supervised-and-correlated`](background-work-runs-supervised-and-correlated.md) | Background Work Runs Supervised, and Every Record Carries One Correlation Id |
| [`background-workers-wake-on-events`](background-workers-wake-on-events.md) | Background Workers Wake on Events, Fall Back Rarely, and Stop When Nothing Needs Them |
| [`background-loops-stop-when-their-task-is-cancelled`](background-loops-stop-when-their-task-is-cancelled.md) | Background Loops Stop When Their Task Is Cancelled, Even If Cleanup Raised Something Else |
| [`platform-differences-live-behind-one-platform-port`](platform-differences-live-behind-one-platform-port.md) | Platform Differences Live Behind One Platform Port; Only macOS Ships |

### Daemon, shell & distribution

| ADR | Decision |
| --- | --- |
| [`daemon-detect-or-spawn`](daemon-detect-or-spawn.md) | Any Surface Finds the Daemon or Spawns It |
| [`daemon-binds-a-fixed-port`](daemon-binds-a-fixed-port.md) | The Daemon Binds a Fixed Port and Refuses to Start Without It |
| [`daemon-is-a-resident-login-service`](daemon-is-a-resident-login-service.md) | The Daemon Is Resident: It Never Idles Out, and a Login Service Restarts Only a Crash |
| [`daemon-auth-and-origin-guard`](daemon-auth-and-origin-guard.md) | A Per-Start Token, Handed to the Page by Whoever Hosts It, Behind a Loopback Host Guard |
| [`stdio-shim-bridge`](stdio-shim-bridge.md) | Agents Reach the Gateway Through a stdio Shim, Not a Native HTTP Entry |
| [`an-installed-daemon-names-the-deployed-shim`](an-installed-daemon-names-the-deployed-shim.md) | An Installed Daemon Names the Deployed Shim |
| [`desktop-shell-over-a-shared-frontend`](desktop-shell-over-a-shared-frontend.md) | The Desktop Shell Hosts the Shared Frontend and Owns Only What a Browser Cannot Do |
| [`daemon-proxies-os-file-actions`](daemon-proxies-os-file-actions.md) | The Loopback Daemon Performs OS File Actions for the UI |
| [`distribution-pyinstaller`](distribution-pyinstaller.md) | Distribution — Four PyInstaller Binaries, Shipped as a CLI Archive and a Desktop App |
| [`project-license-is-agpl-3-0`](project-license-is-agpl-3-0.md) | Coffer Is Licensed Under AGPL-3.0-or-later |
| [`experimental-features-instead-of-a-release-branch`](experimental-features-instead-of-a-release-branch.md) | Experimental Features Instead of a Release Branch |
| [`sidebar-grouped-by-what-the-person-comes-to-do`](sidebar-grouped-by-what-the-person-comes-to-do.md) | The Sidebar Is Grouped by What the Person Comes to Do: Agents, Run, Capabilities, Context, System |

### MCP gateway

| ADR | Decision |
| --- | --- |
| [`session-subprocess-model`](session-subprocess-model.md) | One Upstream Subprocess Set Per Downstream Client Session |
| [`mcp-capability-state-preferences-in-the-vault-lists-live-queried-from-upstream`](mcp-capability-state-preferences-in-the-vault-lists-live-queried-from-upstream.md) | MCP Capability State: Preferences in the Vault, Lists Live-Queried From Upstream |
| [`tool-overload-tier-the-list-search-the-rest`](tool-overload-tier-the-list-search-the-rest.md) | Tool Overload: List a Usage-Ranked Slice, Search the Rest |
| [`tool-search-cuts-cjk-text-into-bigrams`](tool-search-cuts-cjk-text-into-bigrams.md) | Tool Search Cuts CJK Text Into Bigrams |
| [`tool-search-indexes-parameter-text`](tool-search-indexes-parameter-text.md) | Tool Search Indexes Parameter Text |
| [`eval-capture-and-regression-gate`](eval-capture-and-regression-gate.md) | Evals: Opt-In Capture, Hand Curation, and a Deterministic Regression Gate |
| [`record-tool-call-content-redacted-and-bounded`](record-tool-call-content-redacted-and-bounded.md) | Record Tool Call Content, Masked Where the Secrets Are Known and Cut at 16 KB |
| [`custom-tool-pages-give-testing-and-environments-their-own-tabs`](custom-tool-pages-give-testing-and-environments-their-own-tabs.md) | A Custom Tool's Test and a Group's Environments Each Have Their Own Tab |
| [`what-an-agent-fills-in-a-custom-tool-is-an-input`](what-an-agent-fills-in-a-custom-tool-is-an-input.md) | What an Agent Fills in a Custom Tool Is an Input; Query Parameters Are Only the URL's |
| [`a-body-template-is-laid-out-by-its-tokens`](a-body-template-is-laid-out-by-its-tokens.md) | A Body Template Is Laid Out by Its Tokens, Never Parsed |

### Agents & providers

| ADR | Decision |
| --- | --- |
| [`agent-descriptor-manifest`](agent-descriptor-manifest.md) | Per-Agent Behaviour Lives in One Descriptor Record per Agent |
| [`agent-mechanisms-are-optional-facets-on-the-descriptor`](agent-mechanisms-are-optional-facets-on-the-descriptor.md) | Agent Mechanisms Are Optional Facets on the Descriptor, and Projection Is One Registry |
| [`writing-agent-native-config-safely`](writing-agent-native-config-safely.md) | Writing Agent-Native Config Safely |
| [`provider-connections-projected-into-agent-config`](provider-connections-projected-into-agent-config.md) | LLM Connections Are Projected Into Each Agent's Own Config File |
| [`api-key-providers-are-reached-through-a-separate-local-model-proxy`](api-key-providers-are-reached-through-a-separate-local-model-proxy.md) | API-Key Providers Are Reached Through a Separate Local Model Proxy That Relays Bytes Unchanged |
| [`one-connection-serves-both-wires`](one-connection-serves-both-wires.md) | One Connection Serves Both Wires: an Optional Anthropic Address Beside the Base URL |
| [`provider-reach-is-what-its-addresses-serve`](provider-reach-is-what-its-addresses-serve.md) | A Connection Reaches the Agents Its Addresses Serve; No Scope, No Off Switch |
| [`context-windows-for-provider-models`](context-windows-for-provider-models.md) | A Provider Model's Context Window Comes From You, Then the Endpoint, Then the Bundled List, Else Nothing |
| [`usage-is-metered-at-the-proxy-and-subscriptions-show-only-official-quota`](usage-is-metered-at-the-proxy-and-subscriptions-show-only-official-quota.md) | Usage Is Metered at the Proxy; Subscription Agents Are Not Metered |
| [`model-catalogue-read-from-the-agent`](model-catalogue-read-from-the-agent.md) | The Model Catalogue Is Read Back From the Installed Agent |
| [`internal-engine-settings`](internal-engine-settings.md) | The Speech-to-Text Model Is a Setting; Its Endpoint Is Borrowed From a Flagged Connection |

### Chat & channels

| ADR | Decision |
| --- | --- |
| [`driving-agents-through-sdk-and-app-server`](driving-agents-through-sdk-and-app-server.md) | Coffer Drives Claude Code Through the Agent SDK and Codex Through `codex app-server` |
| [`managed-agents-run-with-full-permissions`](managed-agents-run-with-full-permissions.md) | Managed Agents Run With Full Permissions; Owner Pairing Is the Gate |
| [`chat-single-owner-live-mirror`](chat-single-owner-live-mirror.md) | Chat Is a Single-Owner Live Mirror |
| [`channel-adapter-framework`](channel-adapter-framework.md) | Channels Are Thin Transport Adapters Over One Shared Core, Supervised In-Daemon |
| [`channels-are-machine-local-resources`](channels-are-machine-local-resources.md) | Channels Are Machine-Local Resources, Like Agents |
| [`channel-owner-gate`](channel-owner-gate.md) | A Channel Answers Only Its Paired Owner, and Fails Closed in Groups |
| [`channel-conversation-identity`](channel-conversation-identity.md) | A Channel Conversation Is Keyed by (Channel, Chat, Thread); a Direct Chat Is One Conversation Until `/thread` Opens Another |
| [`idle-time-rolls-over-a-direct-chat-but-never-a-thread`](idle-time-rolls-over-a-direct-chat-but-never-a-thread.md) | Idle Time Rolls Over a Direct Chat's Conversation, but Never a Thread's |
| [`channel-thread-context-is-a-bounded-slice`](channel-thread-context-is-a-bounded-slice.md) | A Channel Turn Folds a Bounded Slice of Its Thread, Read by the Transport |
| [`a-burst-of-channel-messages-is-one-turn`](a-burst-of-channel-messages-is-one-turn.md) | A Burst of Channel Messages Is One Turn, Released After a Per-Channel Quiet Window |
| [`channel-switches-structural-vs-parametric`](channel-switches-structural-vs-parametric.md) | Channel Switches: the Agent Opens a New Conversation, the Model Applies Next Turn |
| [`channel-live-surface-strategy`](channel-live-surface-strategy.md) | A Channel Turn Shows Progress on a Preview Surface Where One Exists, and the Reply Is the Answer Alone |
| [`channel-attachments`](channel-attachments.md) | Channel Attachments: Bytes on Disk, a Reference in the Message, Materialised per Agent at Send |
| [`channel-prompt-fixed-note-and-editable-style`](channel-prompt-fixed-note-and-editable-style.md) | A Channel's System Prompt Is a Fixed Channel Note Plus a Reply Style the Owner Can Rewrite |
| [`long-channel-reply-is-rewritten-short`](long-channel-reply-is-rewritten-short.md) | A Long Channel Reply Is Rewritten Short by the Agent |
| [`channel-help-is-a-list-and-cards-carry-only-their-own-actions`](channel-help-is-a-list-and-cards-carry-only-their-own-actions.md) | Channel `/help` Is a List to Read, and a Card Carries Only the Buttons That Act on It |
| [`held-channel-messages-are-continued-or-discarded`](held-channel-messages-are-continued-or-discarded.md) | Held Channel Messages Are Settled by Continue and Discard |
| [`ask-in-the-reply-not-in-a-card`](ask-in-the-reply-not-in-a-card.md) | An Agent Asks the Owner in Its Reply, Not in a Question Card |
| [`a-reply-names-its-files-and-they-follow-it`](a-reply-names-its-files-and-they-follow-it.md) | A Channel Reply Names Its Files, and the Files Follow It |
| [`chat-attachment-uploads`](chat-attachment-uploads.md) | The Chat Page Uploads a File First and Sends Its Id, Into a Sibling Media Directory |
| [`seatalk-websocket-inbound`](seatalk-websocket-inbound.md) | SeaTalk Inbound Is One Outbound WebSocket, Through an Operator-Supplied SDK |
| [`telegram-long-polling`](telegram-long-polling.md) | Telegram Inbound Is a Long Poll That Commits the Offset After Dispatch |

### Skills, knowledge & memory

| ADR | Decision |
| --- | --- |
| [`cross-platform-skill-delivery`](cross-platform-skill-delivery.md) | Skills Reach an Agent as a Directory Link to One Master Folder |
| [`coffer-ships-its-own-skill`](coffer-ships-its-own-skill.md) | Coffer Ships Its Own Manual as a Skill Resource |
| [`knowledge-is-plain-files`](knowledge-is-plain-files.md) | Knowledge Is a Directory of Markdown Files, Not an Index |
| [`tidying-knowledge-is-the-agents-job`](tidying-knowledge-is-the-agents-job.md) | Tidying Knowledge Is the Agent's Job, One Hand-Off Recorded as One Change |
| [`knowledge-is-a-wiki-of-pages-compiled-from-kept-sources`](knowledge-is-a-wiki-of-pages-compiled-from-kept-sources.md) | Knowledge Is a Wiki of Pages Compiled From Kept Sources |
| [`knowledge-stays-current-through-flags-coffer-computes`](knowledge-stays-current-through-flags-coffer-computes.md) | Knowledge Stays Current Through Flags Coffer Computes and an Agent Clears |
| [`knowledge-sources-keep-their-images-and-originals-stay-on-this-mac`](knowledge-sources-keep-their-images-and-originals-stay-on-this-mac.md) | Knowledge Sources Keep Their Images; Originals Stay on This Mac |
| [`knowledge-files-stay-where-their-writer-put-them`](knowledge-files-stay-where-their-writer-put-them.md) | Knowledge Files Stay Where Their Writer Put Them, and Every Link Is Checked |
| [`confluence-pages-import-as-readable-sources`](confluence-pages-import-as-readable-sources.md) | Confluence Pages Import as Readable Sources With Their Attachments |
| [`linked-knowledge-folders-are-read-only-and-machine-local`](linked-knowledge-folders-are-read-only-and-machine-local.md) | A Linked Knowledge Folder Is Shared in Place, Read-Only to Coffer, and Recorded Machine-Local |
| [`sync-memory-into-each-agents-own-memory`](sync-memory-into-each-agents-own-memory.md) | Sync Memory Into Each Agent's Own Memory Through a Hub in the Vault |
| [`global-memories-in-claude-code-live-in-a-global-project`](global-memories-in-claude-code-live-in-a-global-project.md) | Global Memories Live in a Claude Code Project of Their Own, Pointed at From a Rules File |
| [`file-a-memory-where-its-agent-filed-it`](file-a-memory-where-its-agent-filed-it.md) | File a Memory Where Its Agent Filed It |
| [`curate-claude-memory-in-the-open`](curate-claude-memory-in-the-open.md) | Curate Claude Code's Memory in the Open, and Turn Auto Dream On Only When Asked |
| [`codex-memory-identity-is-content-with-rewrite-carry-over`](codex-memory-identity-is-content-with-rewrite-carry-over.md) | A Codex Memory Is Identified by Its Content, and a Rewrite Keeps the Identity |
| [`memory-page-lists-memories-by-scope`](memory-page-lists-memories-by-scope.md) | The Memory Page Lists the Memories by Scope; the Sync Shows Only When It Needs the Person |

### Sync & secrets

| ADR | Decision |
| --- | --- |
| [`sync-applies-clean-merges-and-stops-on-any-conflict`](sync-applies-clean-merges-and-stops-on-any-conflict.md) | Sync Only Pulls and Pushes the Vault Repository; a Clean Merge Is Applied, Any Conflict Stops for the Person |
| [`sync-deletion-breaker`](sync-deletion-breaker.md) | A Sync Round That Would Lose Too Much Is Held, in Both Directions, Counting Losses Not Moves |
| [`sync-machine-identity`](sync-machine-identity.md) | A Machine Is Identified by a Hash of Its Host's Own ID, and Owns One Descriptor in the Tree |
| [`sync-withholds-derived-output`](sync-withholds-derived-output.md) | Sync Withholds Derived Output; Each Machine Renders Its Own |
| [`master-key-lives-in-the-macos-keychain`](master-key-lives-in-the-macos-keychain.md) | The Master Key Lives in a Keychain Access Group Only Coffer's Signed Binaries Can Read; Secrets Stay Envelope-Encrypted in the Vault |
| [`credential-references`](credential-references.md) | Resources Cite Secrets by Opaque Reference, Resolved Only at the Moment of Use |
| [`secrets-cross-machines-only-as-ciphertext`](secrets-cross-machines-only-as-ciphertext.md) | Secrets Cross Machines Only as Ciphertext; the Master Key and the Push Token Never Enter the Repository |
| [`standalone-secrets-are-named-references-injected-into-one-child`](standalone-secrets-are-named-references-injected-into-one-child.md) | Standalone Secrets Are Named `coffer://secret/` References, Injected Only Into One Child Process |
| [`a-secret-header-stores-the-credential-and-its-slot-names-the-scheme`](a-secret-header-stores-the-credential-and-its-slot-names-the-scheme.md) | A Secret Header Stores the Credential Alone, and Its Slot Names the Auth Scheme |
| [`only-a-present-human-sees-a-secret-or-sends-it-somewhere-new`](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md) | Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New |
| [`one-replace-dialog-for-every-secret`](one-replace-dialog-for-every-secret.md) | One Replace Dialog for Every Secret a Resource Uses, Shown Inline in Edit Dialogs |

### Documentation

| ADR | Decision |
| --- | --- |
| [`docs-screenshots-are-generated-from-a-seeded-daemon`](docs-screenshots-are-generated-from-a-seeded-daemon.md) | Docs Screenshots Are Generated From a Seeded Daemon, Not Captured by Hand |
