---
title: Writing skill libraries
description: Structure a library of Coffer-delivered skills so one body serves every organisation, with environment differences in profiles and platform mechanics left to carrier skills.
---

# Writing skill libraries

A single skill is easy to write. A library of them, delivered to several agents and used across more than one organisation or project, needs rules. Without them the same method gets copied into five skills, a platform's command reference ends up pasted into a workflow, and every skill quietly hard-codes one company's hosts and naming conventions.

This page describes how to structure such a library: what kinds of skill there are, how environment differences are expressed, how a skill folder is laid out, and how a library is authored and delivered through Coffer. For the skill format itself and how Coffer stores and delivers skills, see [Skills](/guides/skills).

## Two kinds of skill

Every skill in the library is one of two kinds.

| | Product domain | Carrier |
| --- | --- | --- |
| Owns | A **method**: how to do a job well, independent of any platform | A **platform's mechanics**: hosts, credentials, commands, API shapes |
| Examples | Investigating an incident from logs, submitting a change for review, filing a ticket, verifying a deployed change | A log platform's CLI, a ticket tracker's API, a container platform, a database portal |
| Varies by organisation? | No. Differences live in its profiles | Yes. It *is* the organisation-specific part |
| Has `profiles/` | Yes | No; connection details live in `connection.md` |

A product domain decides *what* should happen: which service a clue points to, how wide a time window to search, what a review request's title must look like. It hands the *how* to a carrier that the resolved profile names. The same product body then works against a different log platform or ticket tracker by changing one profile value.

A carrier knows one platform well and nothing about method. It can be a skill you write, or one another team ships.

### Delegation is a real skill call

When a product domain needs a platform operation, it invokes the carrier. It never copies the carrier's instructions into its own body. Two reasons:

- **Attribution.** A carrier skill may carry its own hooks, usage tracking or permission checks. They fire only when the skill is actually invoked. Reproducing its commands inline bypasses them.
- **Rot.** A carrier changes with its platform. A copy of its commands inside your body goes stale on the carrier's next release, and nothing tells you.

The same goes for reference material. A product domain never carries a platform's query-language syntax or flag reference. Where a step needs the exact syntax, it asks the carrier. The profile may *name* the language (`query_language: <name>`) so the method can mention it, but the syntax stays with the carrier.

### Carrier values

A profile names a carrier with one of these forms:

| Value | Meaning |
| --- | --- |
| `Skill(<name>)` | Invoke that skill as a genuine skill call. Never reproduce its commands. |
| `Skill(<plugin>:<name>)` | A skill shipped inside an agent plugin, which the agent lists with the plugin's prefix. Same rule: invoke it, never copy it. |
| `<domain-name>` | Another domain in this library. Load its `SKILL.md` and follow its routing table. |
| a bare command, e.g. `gh` | Call that CLI directly. |
| `local-file` | No platform; write to disk. |
| `none` | No carrier is known for this environment. Say so and ask the user. |

A domain may need more than one carrier-shaped key when two capabilities do not live on the same platform. Searching logs and mapping a clue to the service that owns it are different jobs, so a log-investigation domain reads `carrier` for the first and `service_lookup_carrier` for the second. A deploy domain reads `deploy_trigger` to start a pipeline and `carrier` to inspect what is actually running. Never assume that a carrier which does one thing on a platform also does a neighbouring thing.

Before naming a carrier in a profile, read that carrier's own `SKILL.md` and confirm it documents the operations your body will ask of it. When it cannot do something the body needs, record the gap in the profile (for example a list of fields the tracker's carrier cannot set) and make the body tell the user, rather than silently dropping the value or inventing a call.

## Profiles

A product domain keeps its **method** in its body and takes everything about the **environment** from a profile: which carrier to call, which hosts belong to the organisation, what environments exist, how branches and titles are named. The body reads keys; the profile supplies values. Swapping the environment never means editing the body.

### Flat profiles, one override

A domain's `profiles/` folder holds `default.md` plus one file per environment you actually work in:

```text
profiles/
  default.md        every key the body reads, with a generic value or none
  <org>.md          one environment: its hosts and every value that differs
  <org>-<other>.md  another environment, added only when one exists
```

There is no inheritance between environment files. Each one is complete for its environment, so a value is always either in that file or in `default.md`, and nothing else. When a second environment inside the same organisation turns up, it gets its own sibling file rather than a layer on top of the first; copying a few lines between two files is cheaper than a merge chain nobody can predict.

Resolution is a single override: take `default.md`, then replace every key the selected environment file sets. A mapping merges key by key; a scalar or a list replaces the default outright.

### Selecting the environment

Every domain's `SKILL.md` carries the same paragraph, word for word:

> **Profile.** Read `profiles/default.md`. Then pick an environment: the one the user names for this request; otherwise the profile whose `remote_hosts` lists the host of the current repository's `origin` remote (`git remote get-url origin`); otherwise none. If an environment was picked, read its file and let every key it sets replace the default. Use the merged values for the rest of this skill; never mix values from two environment files.

Keeping it identical across the library means one rule to learn and one place to change; the portability lint checks that the paragraph has not drifted.

### Profile files are data

Frontmatter holds the settings. The body of the file is at most a few lines saying what the environment is. Explain a non-obvious value with a one-line YAML comment next to it:

```markdown
---
remote_hosts: [git.example.com]
carrier: Skill(example-log-search)
service_lookup_carrier: none   # no verified clue-to-service lookup exists yet
query_language: <name>
timezone: <area>/<city>
branch:
  format: "{author}/{type}/{ticket}/{slug}"
---

# <org>

The organisation's log platform, reached through its own skill.
```

Longer design reasoning — why a key exists, why it is split from another — belongs in this guide or in the domain's design record, not in a file an agent reads on every run.

### Keys belong to a domain

Each domain defines its own keys, and `default.md` declares every one of them, even when the value is `none`. Keys are named for what the body needs (`carrier`, `review.title_template`, `layers.api`), never for a particular platform. Several values that describe the same environment in different systems — a ticket project key, a data platform's project code — are ordinary keys in that environment's file, not separate layers.

### Honest values: `none` and `ask`

A value of `none` is a statement: no environment has named a carrier or source for this yet. A body that reads `none` says which key is unset and asks the user. It never falls back to a carrier that happens to be nearby, and it never guesses.

`ask` works the same way for conventions: `local_path: ask` or `version_signal: ask` means the convention is unknown, so the body asks, and does not promote the answer into a standing convention.

When a key a body needs is absent altogether, the body names the key and the file that should define it, then stops.

## Folder layout

```text
<domain>/
  SKILL.md                    routing only; under 500 lines
  sub-skills/<intent>/SKILL.md
  functions/NN-<step>.md      only for a domain with one ordered flow
  references/<topic>.md
  profiles/default.md
  profiles/<org>.md
  scripts/lint_portable.py
  scripts/test_*.py
  agents/openai.yaml          optional interface metadata for Codex
```

| Part | Contains |
| --- | --- |
| `SKILL.md` | Frontmatter, the standard Profile paragraph, a routing table from user intent to sub-skill or function, and a Boundaries section. No workflow steps. |
| `sub-skills/` | Things a user would ask for on their own. Each has its own `SKILL.md` with `name` and `description`. |
| `functions/` | Ordered steps of one flow that nobody invokes alone. Numbered by position. |
| `references/` | Method and policy shared by several sub-skills or functions in this domain: a playbook, a schema, safety rules. |
| `profiles/` | `default.md` and one file per environment (see [Profiles](#profiles)). The only place organisation-specific strings may appear. |
| `scripts/` | Deterministic checks, each with tests. |
| `connection.md` | Carriers only: hosts, credential locations, backends. |

The test for `sub-skills/` versus `functions/`: would someone ask for this by itself? "Open a review request" and "which service owns this path" are sub-skills. "Run preflight" or "execute case 3" only make sense inside a plan already in hand, so they are functions. A domain can have both; a test-orchestration domain has eight numbered functions and one sub-skill for validating a plan file without running it.

### Frontmatter

```yaml
---
name: <domain>
description: "Use when … NOT … — that is <other-domain>."
metadata:
  profiles: [default, <org>]
  requires: [<base-skill>]
---
```

`metadata.profiles` indexes the profile files the domain ships. `metadata.requires` is covered under [Declared dependencies](#declared-dependencies). Quote a description that contains `: ` (colon and space); unquoted, it is invalid YAML and the skill fails to parse. Keep the description to 1024 characters at most; Coffer refuses to import a longer one.

### Folder hygiene

- **No virtualenv inside the skill.** A venv contains symlinks that resolve outside the folder, and Coffer refuses to import a folder with any such link. Keep it outside, for example `~/.cache/coffer-skill-venv`, and document the one-line rebuild in `SKILL.md`.
- **No test caches.** Point pytest's `cache_dir` outside the folder and run with `PYTHONDONTWRITEBYTECODE=1`.
- **No secrets.** Credentials live in a credential store or a file such as `~/.coffer/secrets/<name>.env` with mode 600. `connection.md` says where; it never holds the value. A skill folder travels through vault sync into git.

## Descriptions

An agent picks a skill from its description alone, so descriptions carry the routing. Every description says three things:

1. **When to use it**, in the words a user would actually say.
2. **Where the variation comes from**: "come from a profile, so one body serves every log platform".
3. **What it is not, and where to go instead.**

The third is the same-capability ambiguity rule. Wherever two skills could plausibly answer the same request, both descriptions draw the line and name each other:

> NOT for entering a single already-known container to read its logs — that is the container domain. NOT a syntax reference for the platform's query language — ask the carrier for that.

A sub-skill's description does the same within its domain. Repeat the boundary in the Boundaries section of `SKILL.md`, where you can explain the reasoning.

## Portability

A product body contains zero organisation-specific strings outside `profiles/`: no internal hostnames, no service names, no ticket prefixes, no user paths, no platform brand names. If a step needs such a value, it reads a profile key.

`scripts/lint_portable.py` enforces this. It scans every `.md` and `.txt` file outside `profiles/`, case-insensitively, against a list of forbidden tokens plus patterns for families of names too large to list one by one, and exits 1 with file, line and match for each hit. The `metadata:` block of frontmatter is exempt, because a list of profile names is an index, not an instruction. `name` and `description` are still scanned.

Run it after every edit. When it flags a legitimate word, adjust the pattern deliberately; a visible false positive is better than a silent leak.

The same script also checks that `SKILL.md` carries the standard Profile paragraph unchanged. Because each skill is delivered on its own (see below), each domain carries its own copy of `lint_portable.py` and its tests; keep the copies identical across the library.

## Shared base skills, never shared file paths

When several domains use the same method (how to gather evidence, how to write a findings report), put that method in its own small **base skill** and have each domain load it by name through the agent's skill mechanism, for example Claude Code's Skill tool.

Never reference another skill's files by relative path, such as `../other-skill/references/report.md`. Coffer delivers each skill to each agent independently, according to that skill's own reach. The other folder may not exist for the agent reading your skill, and the path fails without a clear error.

A base skill's description says it is loaded by other domains, not by users directly:

```yaml
description: "Evidence and report rules shared by investigation domains. Loaded by those domains when they write findings; not something a user asks for directly."
```

A library typically needs two: one for **evidence and reports** (quote evidence verbatim, mask secrets, report only the evidence layer you reached, brief and detailed report templates, try a carrier before calling it unreachable) and one for **guarding writes** (preview, confirm this change now, confirmation does not extend, never retry an uncertain write, read back, use the tool's front door). Every domain that reports or writes loads them instead of restating the rules.

Within one skill, relative paths are fine: `references/`, `profiles/` and `scripts/` travel together.

## Declared dependencies

A skill that loads another skill declares it:

```yaml
metadata:
  requires: [<base-skill>]
```

The declaration is for people: when you change a base skill, `grep -l "requires:.*<base-skill>"` across the library lists every domain to re-check, and when you set a skill's reach, extend the base skill's reach to the same agents. Coffer does not enforce it.

At run time, if loading a required skill fails, the body says so and names the skill. It never improvises a substitute for the missing method.

Carriers named by profile values are not listed in `requires`; they vary by environment and are covered by the `none` rule instead.

## Runtime discipline

These rules go into every product body, usually in the Boundaries or Notes section.

### Try before claiming a capability is missing

Before telling the user that something cannot be reached or is not authorised, invoke the carrier the resolved profile names and quote the error it actually returns. An agent's list of connected tools is not evidence: an unrelated, unauthorised connector for the same kind of document can be listed while the skill that does work is installed and never tried. That failure looks like a permissions problem to the user, and it is not one.

### Front doors only

A carrier's safety checks live in its commands. Call the commands; never import a script's internals or call its API directly to get around a check. When you write a CLI for a carrier, do not export a client that can send a write without passing through the command layer, and test that it cannot.

### Evidence survives brevity

Findings quote their key evidence verbatim: the log line, the error body, the row. Trim it to the relevant part, mask secrets, and keep timestamps and IDs. This holds even when the reply must be short, as in a phone chat. Shorten the prose around the evidence, never the evidence itself. A summary without the line it rests on cannot be checked.

### Say what you could not resolve

When a template placeholder, a profile key or a required input cannot be resolved, name it and stop. Never invent a value that a team will read as a commitment, such as a reviewer, a date or a ticket key.

## Orchestrator domains

Some product domains drive other domains rather than a single carrier. A domain that verifies a deployed change end to end touches an API, a database, a container platform and a log platform, each already served by its own domain. It owns the flow and the safety policy, and delegates each layer.

### Layers map to domains through the profile

```yaml
layers:
  api: <api-domain>
  db: <database-domain>
  container: <container-domain>
  logs: <log-investigation-domain>
deploy_confirm: <deploy-domain>
environments:
  candidates: [test, staging, live]
  default: test
  per_call_confirm: [live]
```

In `default` every layer is `none`: there is no universal API-testing tool. A function that reaches a layer whose key is unset names the key and asks which tool performs that layer. Keep related-but-distinct judgments on separate keys: `deploy_confirm` ("is this the right code") is separate from `layers.container` ("what is this container doing"), even when one platform answers both.

An orchestrator never re-implements a layer. If a request only needs one layer, route the user to that layer's domain instead of running the whole flow.

### Gates

Write the flow as numbered functions with explicit gates between them:

| Gate | Rule |
| --- | --- |
| Plan review | The plan is written and shown; nothing runs until the user approves or edits it. Only read-only checks may run before this gate. |
| Mutation confirmation | Every mutating call is confirmed. In an environment on `per_call_confirm`, every call, every time. Elsewhere the user may pre-authorise a reviewed plan's mutations in one batch. Plan approval never counts as mutation confirmation. |
| Restoration | Every executed mutation is torn down, baseline is verified, residue is reported. Never skipped, even on an aborted run. |

### Read-only and mutation discipline

- Classify every step as read-only or mutating up front. Each mutating case in a plan carries its own teardown.
- The orchestrator is a pure tester: when it finds an environment defect, it stops, reports the defect and suggests a fix. It does not run DDL, change config or restart a service to unblock itself.
- Preconditions are confirmed, not produced. A verification domain confirms the change is deployed through the deploy domain; it never triggers a deploy.
- Put the plan's schema in `references/` and validate it with a script, so a malformed plan fails before anything runs.

## Authoring workflow

Author outside Coffer's master store. `coffer skill add` copies a folder into `~/.coffer/skills/`; authoring inside the store would mean importing a folder onto itself.

```sh
# 1. Author and test in the authoring root
cd ~/.coffer/skill-src/<domain>
~/.cache/coffer-skill-venv/bin/pytest -q scripts
~/.cache/coffer-skill-venv/bin/python scripts/lint_portable.py .

# 2. Import into the master store; Coffer validates and delivers it
coffer skill add ~/.coffer/skill-src/<domain>

# 3. Confirm delivery
coffer skill verify
```

After the first import, keep the authoring root as the source of truth:

- For a real change, edit the authoring root, run the tests and the lint again, then `coffer skill add --force ~/.coffer/skill-src/<domain>`.
- For a quick fix, edit the file in the master folder that `coffer path skill <domain>` prints; agents see the change on their next read. Apply the same change to the authoring root, or the next `coffer skill add --force` overwrites it.
- `coffer skill verify` reports drift between the master and each agent's delivered link, and `--fix` repairs missing or re-pointed links.

When a new domain replaces older single-purpose skills, remove the old ones with `coffer skill rm` only after the new domain has worked end to end, then confirm no stale links remain in the agents' skill folders.

## Designing a new domain

1. **Name the method.** Write one sentence for what the domain owns that no platform owns. If you cannot, it is a carrier.
2. **Find the neighbours.** List every skill that could answer the same request, and write the NOT-clauses in both directions.
3. **Split intents.** Decide which steps a user asks for alone (`sub-skills/`) and which only exist inside one flow (`functions/`).
4. **List the profile keys.** Every host, name, convention and carrier the body needs becomes a key. Set `default.md` honestly, with `none` or `ask` where there is no generic answer.
5. **Verify each carrier.** Read the carrier's own `SKILL.md` and confirm it documents what the body will ask of it. Record gaps in the profile.
6. **Write one file per environment you use.** Each is complete on its own; add a sibling file only when a real second environment appears.
7. **Pull shared method into a base skill.** If another domain already has the same rules, extract them, load them by name, and declare `metadata.requires`.
8. **Copy the lint.** Bring `lint_portable.py` and its tests unchanged from an existing domain, then add any domain-specific validator with its own tests.
9. **Write the body.** Keep `SKILL.md` to the Profile paragraph, routing and boundaries. Add the runtime rules: try the carrier before claiming it is missing, quote evidence, name what could not be resolved.
10. **Check it.** Tests pass, the lint is clean, each environment file merged over `default.md` gives the values you expect, the folder has no venv, cache or secret, and required base skills reach the same agents. Then import and verify.

## Related

- [Skills](/guides/skills) — the skill format, import, reach, editing and drift
- [Vault sync](/guides/vault-sync) — how skill folders travel to your other machines
- [Credentials](/guides/credentials)
