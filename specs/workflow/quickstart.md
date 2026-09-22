# Quickstart — Workflow

A workflow turns a template you wrote into a run that advances on its own,
opening a conversation per node, leaving files behind, and stopping at you
whenever something would reach the outside world.

## 1. Write a template

A template is a resource, so it is registered like any other. This one has
three stages — design, code, test — which is a complete flow, not a cut-down
one: Coffer attaches no meaning to a stage, so three is as valid as eight.

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
          "skill": "coffer-writing-td",
          "artifacts": [{ "name": "td.md", "required": true }],
          "approval": "never"
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
          "artifacts": [{ "name": "change-summary.md", "required": true }],
          "approval": "never",
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
          "artifacts": [{ "name": "test-report.md", "required": true }],
          "approval": "never"
        }
      ]
    }
  ]
}
```

Every task owes a deliverable, and a task you give none is read back owing a
`report.md`. That file is the whole of what the task says to the tasks after
it, so it is worth naming on purpose.

When testing finds a code problem there is no route in the template to take:
you retry `implement`, or you add a task that fixes what was found. Nothing
that already passed is discarded either way. The judgement — redo the code, or
redo the design — is one only whoever is holding the finding can make, and a
route fixed when you wrote the template would make it in advance and wrongly.

The web UI writes the same thing through the same resource endpoint: the
templates are listed under **Resources → Workflows**, with the other kinds,
because that is what they are. The **runs** are elsewhere, under the agents —
a run is operational state that belongs to one machine and never syncs.

## 2. Start a run

```bash
coffer workflow run create --template small-change --title "Buffer table for int64 userid"
coffer workflow run start <run-id>
```

A template and a title, and that is the whole of it. Coffer makes the run its
own working directory; what the run should read is mounted afterwards, on the
run itself (step 4).

The run now advances by itself. `coffer workflow run show <run-id>` prints where
it is; the web UI's run page shows the same thing as a map — where the run is,
what it produced, what it reads — with no buttons on it.

## 3. Redirect it from inside the conversation

Every node is a conversation, and that is where you steer it. Open the node that
is running — in the web UI, clicking it opens its conversation page — and say
what changed in ordinary words.

You do not repeat yourself per node — but say it where it will land. A task
opens with an INDEX of the run so far: every earlier task, what became of it,
and the path of each file it wrote. It does not open with anybody else's
conversation. So what you say inside a running task reaches the tasks after it
by way of the deliverable that task writes, which is why the redirect is worth
making while the task is still running rather than after it has finished. If it
has already finished, retry it.

That is also what keeps a forty-task delivery startable: the index costs a line
per task however long the run gets, where carrying the transcripts forward
costs everything ever said.

The run's own page carries no buttons. Retry, skip, complete — all of it is said
in the node's conversation, where the thing being decided is in front of you.

## 4. Give it something to read

A delivery starts from things that already exist, and you can mount them at any
point — not only at creation:

```bash
coffer workflow run inputs add <run-id> --kind link --ref https://confluence/PRD-118
coffer workflow run inputs upload <run-id> --file ./competitor-analysis.xlsx
coffer workflow run inputs list <run-id>
```

An uploaded file lands under the run's own directory and the agent opens it from
the working directory it runs in. Inputs are *listed* to a node, never pasted in
— a collection can be larger than the whole context budget.

## 5. Decide the writes

When a node's agent calls a tool that writes to Jira, Confluence, GitLab or a
deploy platform, the gateway holds the call and asks you:

```bash
coffer workflow approvals              # what is waiting
coffer workflow approve <approval-id>  # the held call resumes
coffer workflow reject  <approval-id>  # it fails with a reason the node can see
```

The approval appears on the conversation of the node that raised it — where you
are already reading what led to it — and shows the **exact arguments** that will
execute, because a decision on a summary is not a decision. An approval expires; an expired one does not
authorise anything.

The first time a run touches an upstream server, tools Coffer has no judgement
about are held as write-class even when they only read. Answer once and the
judgement is recorded on that server, so it is not asked again.

## 6. Keep what it produced

```bash
coffer workflow run promote <run-id> --collection account-buffer-table
```

The artifacts become a knowledge collection, which the next run can mount as an
input. The run's own directory is untouched.

## Where things are

```text
~/.coffer/workflows/<run-id>/
├── CATALOG.md          # what exists and which node produced it — generated
├── inputs/
└── artifacts/<node>/<attempt>/
```

Plain files. Nothing indexes them, and nothing but you and the agents you run
reads them.

## If you are writing tests against this

Set `COFFER_WORKFLOW_ROOT` to a temporary directory. **Unset, it resolves to
your real vault**, and this layer's code creates, moves and deletes directories
under it. The same hazard the knowledge layer's own tests carry, for the same
reason.

## What it will not do

It will not start itself on a schedule, run two nodes at once, or let an agent
drive the engine over MCP — an agent does a node's work; it does not decide the
shape of the run. And the gate is not a sandbox: it covers what Coffer brokers,
so a node's agent with a shell can still reach the network directly. Route
external writes through registered servers if you want the gate to mean
something.
