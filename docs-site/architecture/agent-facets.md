---
title: Agent facets
description: How Coffer keeps everything that differs between coding agents in one record per agent, why the mechanisms are optional facets on that record, how projection is one registry, how an agent is detected, and the gate that keeps agent-specific branches out of the rest of the code.
---

# Agent facets

Coffer manages coding agents it does not own: today Claude Code and Codex. Almost everything Coffer does ends in one of them — an MCP entry written into its config, a skill linked into its skills folder, a model provider projected into its settings, a hook that hands it memory, a chat turn driven through it. This page explains how Coffer keeps the differences between agents in one place, so that supporting another agent, or placing another kind of asset into the agents it has, is an addition rather than a search. Read it before writing anything that behaves differently per agent. The decision and the alternatives weighed are recorded in the ADR [Agent Mechanisms Are Optional Facets on the Descriptor](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/agent-mechanisms-are-optional-facets-on-the-descriptor.md).

## The problem

Two kinds of thing differ between agents.

- **Values.** Where the config directory is, which environment variable moves it, which files Coffer may show and edit, which file holds MCP servers and in which format, where skills go, which program the agent runs as. These are facts about a product.
- **Mechanisms.** How a model provider is written into the agent's settings, how Coffer's session hook is installed, how the agent's native memory is read, how a turn is run on it, how to tell whether it is installed. These are behaviour.

The values have lived in one record per agent for a long time. The mechanisms did not: each one asked "which agent is this?" in its own module. Adding an agent meant finding every such question by search, and a missed one failed only when that agent reached that path. Worse, three places quietly assumed that one model-provider protocol stands for exactly one agent — Anthropic's for Claude Code, OpenAI's for Codex — so a second agent that speaks the same protocol had no way to exist.

## The idea

One record per agent names everything that differs about it. Values sit in the record directly. Mechanisms are **facets**: optional slots on the same record, each filled with an implementation or left empty when the agent lacks that mechanism.

There are four facets:

| Facet | Answers |
| --- | --- |
| Projection | Which assets Coffer can place into this agent, where each lands, and how Coffer's asset is translated into the agent's own shape. |
| Driver | How Coffer runs a turn on this agent. |
| Memory reader | How the agent's native memory is read, read only. |
| Dependency probe | Whether the agent's program is installed here, and which version. |

A missing facet is simply empty, and every consumer already handles absence: an agent with no delivery hook is never offered one, an agent with no driver does not appear in the chat picker.

### Where the implementations live

The record itself is pure data in the domain layer. The implementations are adapter work — they read files, spawn programs, speak an SDK — and each belongs to the part of Coffer that uses it: the provider translation to the provider feature, the delivery hook and the memory reader to the memory feature, the driver to chat, the probe to the agent feature. So the record only **names** the type of each facet, and the implementations are **bound** to it at the composition root, the one place that is allowed to see every feature at once.

Binding never says which agent is which. Each implementation declares the agent it serves, and the binder groups them by that declaration. A second implementation for the same agent is refused at startup. The composition root builds the bound catalogue once and hands it to every service that needs a mechanism; tests build the same catalogue, with the dependency probe replaced by a fixed answer so a test never depends on what the developer happens to have installed.

## Projection is one registry

Projection is the facet with the most in it, because the set of things Coffer places into an agent keeps growing. It is a **registry keyed by asset type and landing point**:

- the **asset type** is what is placed: an MCP entry, a skill, a model provider, a delivery hook — and later rules, commands, subagents and permissions;
- the **landing point** is where it lands: **user** (the agent's own config directory), **project** (inside a repository), or **shared** (a directory several agents read, written once and kept while any reader still wants it). Every entry of the two shipped agents lands at user level today.

Each entry states the file or folder it lands in — always through the agent's config-file allowlist, which is the security boundary for what Coffer may write — a translation from Coffer's asset to the agent's native fragment, and a capability declaration. The declaration is deliberately small: only what a shipped agent actually uses. For a model provider it is the wire protocols the agent's native config speaks, which may be none. For a delivery hook it is the event the hook sits on.

The registry is also the list of targets the [reconciler](/architecture/reconciler) walks: a new asset type is a new entry on the agents that can receive it, not a new service.

### Provider projection without a protocol map

A model provider connection reaches agents through its scope, not through its protocol. Each agent's provider entry declares which protocols its native config speaks, and nothing maps a protocol to one agent. Reverting an agent to its own login names the agent, not a wire.

A provider translation is pure. It returns a plan: the new text of the main file, the files to write before it, and the files to remove after it. Codex's model catalogue is the reason: the catalogue must exist before the settings point at it, and must stay until the pointer is gone, so the agent never reads a pointer to a file that is not there. The same entry also answers whether Coffer's keys are present, which is how the boot check decides that a connection marked active is not really projected — asking the same code that writes the keys means the check can never drift from the writer.

## Drivers are direct

Coffer drives each agent through the structured protocol its vendor offers: Claude Code through its Agent SDK, Codex through its app server. A generic agent protocol is kept for agents that speak it natively and nothing else; it never replaces a direct driver, because for these two it would add a translation layer over the same protocol and hide what the direct one exposes. The chat feature asks every bound driver to build its turn provider once chat's own dependencies exist, so the chat picker lists exactly the agents that have a driver.

## Detection has two signals

A config directory alone is weak evidence that an agent is installed. It survives an uninstall, and a dotfiles checkout can create it on a machine that never had the program. So detection asks two questions:

1. **Is the agent's program on its real `PATH`, and which version is it?** The daemon's own `PATH` is often the truncated one a graphical launch gets, so the probe asks the user's login shell for the `PATH` the agent really runs with — an operating-system question, answered by the [platform port](/architecture/platform) — and merges the inherited one behind it. It then asks the program for its version with a bounded timeout. The version flag needs no login, no network and no config, and the answer is remembered per binary file, so an upgrade is noticed and an unchanged binary is asked once.
2. **Does the config directory exist?**

The combination is one state:

| Program | Directory | State | What it means |
| --- | --- | --- | --- |
| found | present | installed and in use | Can be added and connected. |
| found | absent | installed, never run | Can be added: registering it at its standard directory creates that directory, holding only what Coffer needs there (its `skills` folder). |
| missing | present | config only | What is left of an uninstalled agent; shown as not installed, and cannot be added. |
| missing | absent | missing | Nothing of the type on this machine. |

There is one agent per type, named by it (spec agent-registry "Keep one agent per type, named by it"), so detection is reported per type rather than per directory (spec agent-registry "Report every supported type's detection state"). Every supported type gets one row, registered or not, carrying its state, version, the directory it has or would be registered at, its standard directory and whether it can be added. For each type discovery looks at the standard directory and at the directory the type's own environment variable (`CLAUDE_CONFIG_DIR`, `CODEX_HOME`) names in the daemon's environment, when one is set, and nowhere else. That second directory never becomes a second candidate: it is offered as "use a different config directory" for the one agent, or is the directory Add registers when only it exists. A type that is not registered and is seen by either signal is a candidate, at most one per type. Nothing is stored: the state is read whenever an agent or a candidate is shown.

## Hooks are read, and Coffer's own is checked

An agent runs hooks from its own settings files and from its plugins, and Coffer installs one of its own. Coffer reads all of them, read only: each hook's event, matcher, command and the file that declares it. Both agents keep hooks in the same shape, so one reader serves both; which files carry hooks is a value on each agent's record, and each enabled plugin's hook file is found through the plugin listing. A project's own settings are not read, because Coffer does not know which repositories the agent is used in.

Coffer's own hook is found by its marker and checked the way the boot repair checks it: current when the installed command is exactly the one Coffer would write now, stale when the marker carries some other command, missing when it is not there. The last time it fired comes from the audit log, where every real fire is recorded — "installed" and "has ever run" stay two different facts.

## How the rule is protected

The rule the whole design rests on is that nothing outside the agent record and the facet implementations asks which agent it is dealing with. A build gate, run as part of `make lint` and therefore of every `make verify`, enforces it.

Like the platform gate, it reads the source as a syntax tree rather than searching it as text. It fails the build when code outside the allowed places names a specific agent type, or compares a value with an agent type's literal name — the same branch spelled as a string. Naming the enum to construct a member from a value, or iterating over all agents, is fine: neither says which agent is which. The allowed places are the agent record and its domain, the agent feature's own adapters, the facet implementations other features own (each listed by name in the gate, added in the change that adds it), and the database migrations, which are history. Tests are not scanned.

When the gate fails it names the file, the line and what it objected to.

## When a new agent or asset appears

- **A new agent** is a new agent type, one record with its values, the facet implementations it has, and one child spec. The shared facet contract test — one set of promises every agent's facets must keep, run against a fake config directory for each agent — is how the new agent proves it fits before it ships.
- **A new asset type** is a new registry entry on each agent that can receive it, with its landing point, translation and the smallest capability declaration a shipped agent needs.
- **A new mechanism** that does not fit an existing facet is a design discussion, not a branch: it either extends a facet or earns a new one through an ADR.
