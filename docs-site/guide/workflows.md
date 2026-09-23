# Workflows

A **workflow** is the shape of a delivery, written down once: stages in the order they run and the tasks inside each stage. A **run** is one delivery through that shape. Once you set a run going it moves on by itself: each task gets a conversation with an agent, leaves files behind, and the run stops for you when a tool call would write to the outside world.

The workflow (the template) is a resource like any other kind and syncs with the vault. A run is operational state. It belongs to the machine that created it, never syncs, and is read-only on every other machine.

## Write a workflow

A vault that has never been touched already has one workflow, **ship-a-change**, with five tasks that take one change from a question to a written result. It names no skill and no agent, so it is valid on any machine. It is yours to edit, rename, disable or delete.

To write your own, put the definition in a JSON file and register it:

```bash
coffer workflow template add small-change --file ./small-change.json
```

```json
{
  "description": "One repository, one change, design first",
  "stages": [
    {
      "key": "design",
      "name": "Tech Design",
      "nodes": [
        {
          "key": "draft_td",
          "name": "Draft the technical design",
          "type": "ai",
          "artifacts": [{ "name": "td.md", "required": true }]
        }
      ]
    },
    {
      "key": "coding",
      "name": "Coding",
      "nodes": [
        {
          "key": "implement",
          "name": "Implement the change",
          "type": "ai",
          "artifacts": [{ "name": "change-summary.md" }],
          "on_failure": { "action": "retry", "times": 1 }
        }
      ]
    },
    {
      "key": "testing",
      "name": "Testing",
      "nodes": [
        {
          "key": "verify",
          "name": "Run the checks and report",
          "type": "ai",
          "instructions": "Run the repository's own test commands and write down what failed.",
          "artifacts": [{ "name": "test-report.md" }]
        }
      ]
    }
  ]
}
```

Three stages make a complete flow. Coffer reads no meaning into a stage key, so a three-stage workflow and an eight-stage one run on the same code.

A template has two top-level fields, `description` and `stages`. A stage takes `key`, `name`, `nodes` and an optional `optional` flag. Each task (`nodes[]`) takes:

| Field | Meaning |
| --- | --- |
| `key`, `name` | Required. The key is a lowercase slug (`a-z`, `0-9`, `_`, `-`) and must be unique across the whole template. |
| `type` | Required. `ai` means an agent does the work in a conversation. `manual` means you do it: the run stops at the task and opens no conversation. |
| `skill` | A registered skill the task opens with. A skill this vault does not have is refused. |
| `instructions` | What this task is for, in your own words. |
| `artifacts` | The files the task owes, as `{ "name", "required" }`. `required` defaults to `true`, and a name is a single file name. |
| `approval` | `never` (the default) or `always`. With `always`, the task stops for you when its turn ends instead of completing. |
| `on_failure` | `{ "action": "stop" }` (the default), `continue`, or `retry` with `times` (default `1`). |
| `agent`, `model`, `effort` | Which agent the task runs on, and optionally which model and reasoning effort. An agent outside the template's scope is refused. |
| `attempt_ceiling` | How many attempts this task may open in total. Default `3`. |

**Every task owes a deliverable.** If a task declares no artifacts, it owes a required `report.md` when the run reads it. Your stored template stays as you wrote it. The deliverable is all a task passes on to the tasks after it, so name it on purpose.

**There are no routes between stages.** Sending work back is your call, made during the run. A template that still has an `edges` field is refused and the error names that field. If testing finds a problem in the code, you retry `implement` or add a task that fixes the problem, and nothing that already passed is thrown away. Only whoever is holding the finding can judge whether the code or the design needs redoing. A route written into the template would make that call in advance.

A refused template names the JSON path of the field that is wrong, for example `stages[1].nodes[0].skill`. `coffer workflow template update <name> --file …` replaces a definition. A run that already exists keeps the snapshot it froze when it was created, so editing a template never disturbs work in progress.

In the web UI, workflows are under **Resources → Workflows**. The editor shows every stage in order beside the tasks of the stage you are editing. It derives keys from the names you type and saves each edit as you make it, so it has no Save button. Switching a workflow off stops new runs from it; runs already created are unaffected.

## Start a run

```bash
coffer workflow run create --template small-change --title "Buffer table for int64 userid"
coffer workflow run start <run-id>
```

A template and a title are all a run needs. `--agent` sets the default agent for the run's tasks. The run is created in `draft`, so you can mount what it should read before the first task opens (see below). Coffer gives each run its own working directory, and every task's agent works in it.

`coffer workflow run start` sets the run going, and from then on it moves on by itself. **Runs → New run** in the web UI also creates a run in `draft`. The web UI has no start, pause, resume or abort control, so those signals come from the CLI: `coffer workflow run start|pause|resume|abort <run-id>`.

`coffer workflow run show <run-id>` prints the stages, the tasks and what each task allows now. `run events` prints the event log, and `run artifacts` lists what each task produced. In the web UI, a run's page (under **Agents → Runs**) is a map. **Stages** shows where the run is. **Context** is one list of what the run reads and what it has produced. Clicking a task opens its conversation.

`coffer workflow run relabel <run-id> --title … [--description …]` rewrites a run's labels. Nothing else about the run changes.

## Steer it by talking to a task

Each task is its own conversation, and you steer it there in ordinary words. What you say takes effect according to where the task is:

- **Not started yet**: your words are queued onto the task's first attempt and become part of the brief it opens with.
- **Waiting for review**: your words carry the same attempt on with more to do.
- **Finished** (completed, skipped or failed): your words open the next attempt, within the task's attempt ceiling.

While the task's own turn is running, you are talking to the agent in its conversation.

A task opens with four parts: its brief, including the exact path of each file it owes; its skill's instructions; an **index** of the run so far; and the run's inputs. The index has one line per earlier task, with what became of that task and the path of each file it wrote. It carries the latest attempt of each task, including tasks that failed or were skipped. A task never opens with another task's conversation. So what you say in one task reaches the later ones through the deliverable that task writes. Say it while the task is still running. If the task has already finished, speak to it again to open a new attempt.

The index is also what keeps a long delivery startable: it grows by one line per task, however long the run gets. If even the index outgrows the context budget, the oldest entries are left out and the context says which ones and where the full list is. When one task's own conversation gets too long, its oldest turns are compacted into a summary that stays in the conversation.

A task whose turn ends while it still owes a required file, whose `approval` is `always`, or whose `type` is `manual` stops at **waiting for review**. The web UI lets you talk to it but has no button to let it through. From the CLI:

```bash
coffer workflow node act <run-id> <task-key> complete      # also: start, feedback, retry, skip, restore
coffer workflow node act <run-id> <task-key> complete --waive-artifacts
coffer workflow node add <run-id> --stage testing --name "Fix the flaky test" --instructions "…"
```

`node add` adds unplanned work to a stage. The new task opens with the same four parts as any other task, and its artifacts are attributed to it the same way.

Before a task starts, its conversation page also lets you pick the agent, model and effort it runs on. The choice is recorded against that attempt, so a retry on a bigger model leaves the first attempt's record saying what it actually ran on.

## Give it something to read

You can mount inputs at any point in the run, not only before it starts:

```bash
coffer workflow run inputs add <run-id> link:https://confluence.example.com/display/PRD-118
coffer workflow run inputs add <run-id> knowledge:account-service --label "Service notes"
coffer workflow run inputs add <run-id> repo:~/code/account-service
coffer workflow run inputs upload <run-id> ./competitor-analysis.xlsx
coffer workflow run inputs list <run-id>
coffer workflow run inputs rm <run-id> <ref>
```

- **A link** is listed with what it points at, such as a Confluence page, a Jira issue or a Google doc, when that can be recognised from the address. The task then knows which tool opens it.
- **A knowledge collection** is listed by the path the agent reads it from.
- **A repository** gives the run its own checkout: a git worktree inside the run's working directory, on a `coffer/run-…` branch of its own. Your own checkout and its uncommitted work are never touched. Unmounting removes the worktree and its branch, and nothing else.
- **An uploaded file** is stored under the run's own directory. Its bytes are deleted when you unmount it.
- **A note** is markdown you write into the run's context from its **Context** tab. You can keep editing it for as long as the run exists, and every task sees it as your own words.

Inputs are *listed* to a task, never pasted in. A collection or a repository can be bigger than the whole context budget.

## Decide the writes

When a task's agent calls an upstream tool that writes, such as Jira, Confluence, GitLab or a deploy platform reached through a registered MCP server, the gateway holds the call and asks you:

```bash
coffer workflow approvals                          # what is waiting (--run, --status, --json)
coffer workflow approve <approval-id> -m "ok"      # the held call goes through, once
coffer workflow reject  <approval-id> -m "why"     # it fails, and the task sees your reason
```

The approval appears in the conversation of the task that raised it, under the message that led to it, and it is sent to every enabled [channel](/guide/channels). It shows the **exact arguments** that will execute, because approving a summary is not really a decision. An approval expires after an hour, and an expired one authorises nothing. The held call fails with a reason the agent can read, so it is never silently dropped. Deciding the same approval twice changes nothing and executes nothing twice.

A tool Coffer has no judgement about is held as write-class, even if it only reads. The first run against a new server will therefore stop on reads. In the web UI, tick **Remember … as read-only** when you approve, and Coffer records that on the server so the tool is not held again.

Built-in `coffer__*` tools are never held; they reach your own vault. Ordinary chats and channel conversations are never gated, only a run's tool calls. The gate is not a sandbox. It covers only what Coffer brokers, and a task's agent with a shell can still reach the network directly. If you want the gate to mean something, route external writes through registered servers. [A Workflow Run's Writes Are Gated at the Gateway](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/workflow-gates-tool-calls.md) has the reasoning.

## Keep what it produced

```bash
coffer workflow run promote <run-id> --collection account-buffer-table
```

This copies what the run is made of into a knowledge collection: its artifacts (each named with the task and attempt that wrote it), its uploads and its notes. The links, collections and repositories the run read are written down as one `references.md`. A run that has produced nothing yet can still be promoted, because its brief and inputs may be worth keeping. The run's own directory is left untouched. The next run can mount the collection as an input.

`coffer workflow run delete <run-id>` deletes the run, its events and its directory. The task conversations are kept.

## Where things are

```text
~/.coffer/workflows/<run-id>/
├── CATALOG.md                      # generated list of every artifact and the task that wrote it
├── inputs/                         # uploaded files and your notes
├── workspace/                      # the working directory every task's agent runs in; mounted repositories are checked out here
└── artifacts/<task-key>/<attempt>/<name>
```

These are plain files. Nothing indexes, chunks or embeds them, and a retry never overwrites an earlier attempt's files. The web UI opens any of them from the run's **Context** tab. Reading is bounded: a long file is shown as its head, and a path outside the run's directory is refused.

`COFFER_WORKFLOW_ROOT` moves the root. If you are writing tests against this layer, set it to a temporary directory. **When it is unset, it resolves to your real `~/.coffer/workflows`**, and the workflow code creates, moves and deletes directories there.

## What it will not do

A run never starts on a schedule and never runs two tasks at once. An agent does a task's work, but it does not drive the engine over MCP or decide the shape of the run. There is one owner and one approver: you.

The requirements are in the [workflow spec](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/workflow/spec.md).

[Sync →](/guide/sync)
