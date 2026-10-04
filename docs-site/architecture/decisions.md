---
title: Decision records
description: An index of Coffer's architecture decision records, grouped by area, each stating the decision it records.
---

# Decision records

Coffer records every structural technical decision as an architecture decision record (ADR) in [`docs/decisions/`](https://github.com/wyx-sg/Coffer/tree/main/docs/decisions). This page indexes them by area. Read the record when you want the *why* behind a part of the design, or before you propose a change that would reverse one.

## How decisions are recorded

Coffer keeps three kinds of design text, each with one job:

| Artefact | Lives in | Answers |
| --- | --- | --- |
| Specification | [`openspec/specs/`](https://github.com/wyx-sg/Coffer/tree/main/openspec/specs) | *What* the product must do: requirements, each with scenarios that tests cover. |
| Change proposal | `openspec/changes/<change-id>/` | *How* one change is planned: proposal, design, tasks and spec deltas. |
| Decision record | [`docs/decisions/`](https://github.com/wyx-sg/Coffer/tree/main/docs/decisions) | *Why* a technical choice was made, with every serious option argued. |

A decision earns a record when it is hard to change later, constrains more than one module, carries a trade-off a future contributor will question, or departs from a convention or a clause of the [Principles](/architecture/principles). Product scope belongs in the specs and project process in `.agents/`, not in a record.

Each record states **one** decision under four headings — **Context**, **Options Considered** (the chosen option included, each argued on its merits), **Decision** and **Consequences** — and is named by its title in kebab case, never by a number. The directory records the live design: when a decision changes, the record that owns it is rewritten to read as if written today, with the design it replaced argued as one of its options; when the thing it decided is removed, the record is deleted. The authoring rules are in the [directory README](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/README.md).

Every record carries its own status, and every record listed below is `Accepted`: it is in effect and states the live design. The [directory README](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/README.md) is the authoritative index; when this page and a record's own `Status` line disagree, the record wins.

## Resource framework & persistence

Explained in: [Resource framework](/architecture/resource-framework), [Persistence](/architecture/persistence), [Reconciler](/architecture/reconciler), [Platform port](/architecture/platform).

| Decision | Record |
| --- | --- |
| The Resource Framework Is Core Domain, Designed Before the Second Kind | [`resource-framework-upfront`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/resource-framework-upfront.md) |
| A Kind Plugs In as One Frozen Record of Optional Hooks: Validators Before the Write, Reactions After | [`kind-plugin-contract`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/kind-plugin-contract.md) |
| A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label | [`identity-is-the-uid-inside-the-file`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/identity-is-the-uid-inside-the-file.md) |
| Names Visible to Agents Are Fixed | [`names-visible-to-agents-are-fixed`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/names-visible-to-agents-are-fixed.md) |
| Per-Agent Resource Scope Is One Framework Allow-List, Enforced by Each Kind | [`per-agent-resource-scope`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/per-agent-resource-scope.md) |
| Reach Is Machine-Local: Stored by uid in `local/reach.json`, Never Synced | [`reach-is-machine-local-stored-by-uid-never-synced`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/reach-is-machine-local-stored-by-uid-never-synced.md) |
| Code Layout Is Layer-First, With One Subdirectory per Kind | [`code-layout-layer-first`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/code-layout-layer-first.md) |
| Kinds Are Wired Explicitly by One Composition Root, With No Global Registry | [`composition-root-explicit-wiring`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/composition-root-explicit-wiring.md) |
| Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy | [`storage-is-five-classes-by-nature`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/storage-is-five-classes-by-nature.md) |
| History Is One SQLite File, `runs.db`, Written Only by the Daemon and Migrated Forward at Startup Through One Alembic Lineage | [`history-is-one-sqlite-file-written-only-by-the-daemon`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/history-is-one-sqlite-file-written-only-by-the-daemon.md) |
| Every Vault File Carries Its Own Format Version; One Owner Machine Commits Layout Upgrades | [`every-vault-file-carries-its-format-version`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/every-vault-file-carries-its-format-version.md) |
| Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer | [`every-vault-write-is-a-validated-commit-naming-its-writer`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/every-vault-write-is-a-validated-commit-naming-its-writer.md) |
| Audit Every Change With Its Actor, Log Invocations Without Payloads, Prune Per Table | [`audit-and-retention`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/audit-and-retention.md) |
| One Level-Triggered Reconciler Converges What Coffer Writes Outside Its Database, Comparing Parameters | [`one-level-triggered-reconciler-compares-parameters`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/one-level-triggered-reconciler-compares-parameters.md) |
| The Wire Contract Is Generated From the Pydantic Models, and the Frontend Client From the Contract | [`wire-contract-generated-from-the-pydantic-models`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/wire-contract-generated-from-the-pydantic-models.md) |
| Background Work Runs Supervised, and Every Record Carries One Correlation Id | [`background-work-runs-supervised-and-correlated`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/background-work-runs-supervised-and-correlated.md) |
| Platform Differences Live Behind One Platform Port; Only macOS Ships | [`platform-differences-live-behind-one-platform-port`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/platform-differences-live-behind-one-platform-port.md) |

## Daemon, shell & distribution

Explained in: [Daemon and processes](/architecture/daemon), [Distribution and releases](/architecture/distribution).

| Decision | Record |
| --- | --- |
| Any Surface Finds the Daemon or Spawns It | [`daemon-detect-or-spawn`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/daemon-detect-or-spawn.md) |
| The Daemon Binds a Fixed Port and Refuses to Start Without It | [`daemon-binds-a-fixed-port`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/daemon-binds-a-fixed-port.md) |
| The Daemon Is Resident: It Never Idles Out, and a Login Service Restarts Only a Crash | [`daemon-is-a-resident-login-service`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/daemon-is-a-resident-login-service.md) |
| A Per-Start Token, Handed to the Page by Whoever Hosts It, Behind a Loopback Host Guard | [`daemon-auth-and-origin-guard`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/daemon-auth-and-origin-guard.md) |
| Agents Reach the Gateway Through a stdio Shim, Not a Native HTTP Entry | [`stdio-shim-bridge`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/stdio-shim-bridge.md) |
| The Desktop Shell Hosts the Shared Frontend and Owns Only What a Browser Cannot Do | [`desktop-shell-over-a-shared-frontend`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/desktop-shell-over-a-shared-frontend.md) |
| The Loopback Daemon Performs OS File Actions for the UI | [`daemon-proxies-os-file-actions`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/daemon-proxies-os-file-actions.md) |
| Distribution — Three PyInstaller Binaries, Shipped as a CLI Archive and a Desktop App | [`distribution-pyinstaller`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/distribution-pyinstaller.md) |
| Experimental Features Instead of a Release Branch | [`experimental-features-instead-of-a-release-branch`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/experimental-features-instead-of-a-release-branch.md) |
| The Sidebar Is Grouped by What the Person Comes to Do: Agents, Run, Capabilities, Context, System | [`sidebar-grouped-by-what-the-person-comes-to-do`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sidebar-grouped-by-what-the-person-comes-to-do.md) |

## MCP gateway

Explained in: [MCP gateway](/architecture/mcp-gateway).

| Decision | Record |
| --- | --- |
| One Upstream Subprocess Set Per Downstream Client Session | [`session-subprocess-model`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/session-subprocess-model.md) |
| MCP Capability State: Preferences in the Vault, Lists Live-Queried From Upstream | [`mcp-capability-state-preferences-in-the-vault-lists-live-queried-from-upstream`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/mcp-capability-state-preferences-in-the-vault-lists-live-queried-from-upstream.md) |
| Tool Overload: List a Usage-Ranked Slice, Search the Rest | [`tool-overload-tier-the-list-search-the-rest`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/tool-overload-tier-the-list-search-the-rest.md) |
| Evals: Opt-In Capture, Hand Curation, and a Deterministic Regression Gate | [`eval-capture-and-regression-gate`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/eval-capture-and-regression-gate.md) |

## Agents & providers

Explained in: [Agents](/guides/agents), [Model providers](/guides/providers), [Agent facets](/architecture/agent-facets), [Model proxy](/architecture/model-proxy).

| Decision | Record |
| --- | --- |
| Per-Agent Behaviour Lives in One Descriptor Record per Agent | [`agent-descriptor-manifest`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/agent-descriptor-manifest.md) |
| Agent Mechanisms Are Optional Facets on the Descriptor, and Projection Is One Registry | [`agent-mechanisms-are-optional-facets-on-the-descriptor`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/agent-mechanisms-are-optional-facets-on-the-descriptor.md) |
| Writing Agent-Native Config Safely | [`writing-agent-native-config-safely`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/writing-agent-native-config-safely.md) |
| Coffer's Agent Hooks Are Marker-Scoped, Explicit, Audited and Repaired When Stale | [`agent-hook-installation`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/agent-hook-installation.md) |
| LLM Connections Are Projected Into Each Agent's Own Config File | [`provider-connections-projected-into-agent-config`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/provider-connections-projected-into-agent-config.md) |
| API-Key Providers Are Reached Through a Separate Local Model Proxy That Relays Bytes Unchanged | [`api-key-providers-are-reached-through-a-separate-local-model-proxy`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/api-key-providers-are-reached-through-a-separate-local-model-proxy.md) |
| Usage Is Metered at the Proxy; Subscription Agents Are Not Metered | [`usage-is-metered-at-the-proxy-and-subscriptions-show-only-official-quota`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/usage-is-metered-at-the-proxy-and-subscriptions-show-only-official-quota.md) |
| The Model Catalogue Is Read Back From the Installed Agent | [`model-catalogue-read-from-the-agent`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/model-catalogue-read-from-the-agent.md) |
| The Speech-to-Text Model Is a Setting; Its Endpoint Is Borrowed From a Flagged Connection | [`internal-engine-settings`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/internal-engine-settings.md) |

## Chat & channels

Explained in: [Chat and turns](/architecture/chat), [Channels](/guides/channels).

| Decision | Record |
| --- | --- |
| Coffer Drives Claude Code Through the Agent SDK and Codex Through `codex app-server` | [`driving-agents-through-sdk-and-app-server`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/driving-agents-through-sdk-and-app-server.md) |
| Managed Agents Run With Full Permissions; Owner Pairing Is the Gate | [`managed-agents-run-with-full-permissions`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/managed-agents-run-with-full-permissions.md) |
| Chat Is a Single-Owner Live Mirror | [`chat-single-owner-live-mirror`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/chat-single-owner-live-mirror.md) |
| Channels Are Thin Transport Adapters Over One Shared Core, Supervised In-Daemon | [`channel-adapter-framework`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/channel-adapter-framework.md) |
| A Channel Answers Only Its Paired Owner, and Fails Closed in Groups | [`channel-owner-gate`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/channel-owner-gate.md) |
| A Channel Conversation Is Keyed by (Channel, Chat, Thread) and Grounded in Its Thread and Quote | [`channel-conversation-identity-and-context`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/channel-conversation-identity-and-context.md) |
| Channel Switches: the Agent Opens a New Conversation, the Model Applies Next Turn | [`channel-switches-structural-vs-parametric`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/channel-switches-structural-vs-parametric.md) |
| A Channel Reply Grows on One Live Surface, Paced by the Transport | [`channel-live-surface-strategy`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/channel-live-surface-strategy.md) |
| Channel Attachments: Bytes on Disk, a Reference in the Message, Materialised per Agent at Send | [`channel-attachments`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/channel-attachments.md) |
| The Chat Page Uploads a File First and Sends Its Id, Into a Sibling Media Directory | [`chat-attachment-uploads`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/chat-attachment-uploads.md) |
| SeaTalk Inbound Is One Outbound WebSocket, Through an Operator-Supplied SDK | [`seatalk-websocket-inbound`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/seatalk-websocket-inbound.md) |
| Telegram Inbound Is a Long Poll That Commits the Offset After Dispatch | [`telegram-long-polling`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/telegram-long-polling.md) |

## Skills, knowledge & memory

Explained in: [Knowledge](/architecture/knowledge), [Memory](/architecture/memory), [Skills](/guides/skills).

| Decision | Record |
| --- | --- |
| Skills Reach an Agent as a Directory Link to One Master Folder | [`cross-platform-skill-delivery`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/cross-platform-skill-delivery.md) |
| Coffer Ships Its Own Manual as a Skill Resource | [`coffer-ships-its-own-skill`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/coffer-ships-its-own-skill.md) |
| Knowledge Is a Directory of Markdown Files, Not an Index | [`knowledge-is-plain-files`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/knowledge-is-plain-files.md) |
| Tidying Knowledge and Memory Is the Agent's Job | [`tidying-knowledge-and-memory-is-the-agents-job`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/tidying-knowledge-and-memory-is-the-agents-job.md) |
| Aggregate the Agents' Memory; Never Write It | [`aggregate-agent-memory-never-write-it`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/aggregate-agent-memory-never-write-it.md) |
| Memory Reaches a Session at Three Moments: an Index at Start, Retrieval per Prompt, and a Guard Before a Known Trap | [`memory-reaches-a-session-at-prompt-time-and-before-a-known-trap`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/memory-reaches-a-session-at-prompt-time-and-before-a-known-trap.md) |

## Sync & secrets

Explained in: [Vault sync](/architecture/vault-sync), [Security model](/architecture/security).

| Decision | Record |
| --- | --- |
| Sync Only Pulls and Pushes the Vault Repository; a Clean Merge Is Applied, Any Conflict Stops for the Person | [`sync-applies-clean-merges-and-stops-on-any-conflict`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sync-applies-clean-merges-and-stops-on-any-conflict.md) |
| A Sync Round That Would Lose Too Much Is Held, in Both Directions, Counting Losses Not Moves | [`sync-deletion-breaker`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sync-deletion-breaker.md) |
| A Machine Is Identified by a Hash of Its Host's Own ID, and Owns One Descriptor in the Tree | [`sync-machine-identity`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sync-machine-identity.md) |
| Sync Withholds Derived Output; Each Machine Renders Its Own | [`sync-withholds-derived-output`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sync-withholds-derived-output.md) |
| The Master Key Lives in a Keychain Access Group Only Coffer's Signed Binaries Can Read; Secrets Stay Envelope-Encrypted in the Vault | [`master-key-lives-in-the-macos-keychain`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/master-key-lives-in-the-macos-keychain.md) |
| Resources Cite Secrets by Opaque Reference, Resolved Only at the Moment of Use | [`credential-references`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/credential-references.md) |
| Secrets Cross Machines Only as Ciphertext; the Master Key and the Push Token Never Enter the Repository | [`secrets-cross-machines-only-as-ciphertext`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/secrets-cross-machines-only-as-ciphertext.md) |
| Standalone Secrets Are Named `coffer://secret/` References, Injected Only Into One Child Process | [`standalone-secrets-are-named-references-injected-into-one-child`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/standalone-secrets-are-named-references-injected-into-one-child.md) |
| Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New | [`only-a-present-human-sees-a-secret-or-sends-it-somewhere-new`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md) |
