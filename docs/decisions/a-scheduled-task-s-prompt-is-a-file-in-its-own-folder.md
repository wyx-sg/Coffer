# A Scheduled Task's Prompt Is a File in the Task's Own Folder

**Status**: Accepted
**Date**: 2026-11-11
**Deciders**: Yuxing (owner)
**Related**: [A Scheduled Task Is a Prompt on a Schedule](automation-is-a-scheduled-prompt.md), [A Channel Reply Names Its Files, and the Files Follow It](a-reply-names-its-files-and-they-follow-it.md), [An Agent Notifies the Owner Through a Built-in Tool](an-agent-notifies-the-owner-through-a-built-in-tool.md), spec channels, research note [Scheduled agent tasks](../research/scheduled-agent-tasks.md)

## Context

A task's prompt was a string in its config (`local/resources/scheduled_task/<uid>.json`)
and a task that named no directory ran in Coffer's workspace root,
`~/.coffer/content/workspace`, shared with every chat and channel turn
without one. Using the first real task (a daily report of the owner's
SeaTalk bot), the owner asked on 2026-11-11 for three things:

- the prompt should read "像文件一样", rendered as Markdown and editable;
- a report should be a file they can open later, not only a message in their
  SeaTalk DM;
- the detail page should split into tabs, with the run history as a table.

Where the prompt lives and where a run's files land are one technical point:
both decide what a task owns on disk.

## How comparable products do it

- **Claude Code Desktop scheduled tasks.** Each task is a folder,
  `~/.claude/scheduled-tasks/<name>/SKILL.md`: the body is the prompt, edited
  in the app or in any editor, read again at the next run. Schedule, folder
  and model live outside the file.
- **Codex automations.** The prompt is a form field (or comes from a skill).
  A run's changes stay in its working directory or worktree.
- **Manus automations.** A task may keep updating one artefact (a document, a
  board) instead of producing a new one each run.
- **GitHub Actions** (a reference, not an agent product). The workflow is a
  file in the repository; a run may upload artifacts, kept per run.

## Options Considered

### Where the prompt lives

#### A — `PROMPT.md` in the task's own folder (chosen)

`~/.coffer/content/workspace/scheduled-tasks/<uid>/PROMPT.md`. The config no
longer carries it; the page reads and writes the file, and so can any editor
or agent. A run reads the file as it is when it starts.

- **Good:** the prompt is a file like Claude Code's `SKILL.md`, so Markdown,
  any editor and an agent editing its own task all work with nothing added;
  long prompts stop bloating the resource file; the folder is the natural home
  for what the task produces.
- **Costs:** the prompt is no longer validated on every write: a file emptied
  by hand is found only when the run starts, and that run fails saying so. A
  task is now two places (config and folder), so tasks written before
  2026-11-11 are migrated at startup, and a config carrying `prompt` is
  refused rather than silently ignored.

#### B — Keep the prompt in the config; only show it as a file

- **Good:** nothing on disk changes; one write path.
- **Lost because:** the owner asked for it to be a file, and a string shown as
  one cannot be opened in an editor or edited by an agent with its own file
  tools.

#### C — A `SKILL.md` per task, as Claude Code does

- **Lost because:** a task's prompt is not a skill (no frontmatter, no tool
  grants, not delivered to agents), and naming it `SKILL.md` would make the
  skill tooling treat it as one.

### Where a run works when the task names no directory

#### A — The task's own folder (chosen)

- **Good:** what a run writes (a dated report, a CSV) stays beside its prompt
  and appears in the task's Files tab with no setup; two tasks never write
  over each other's files.
- **Costs:** a task that should work in a repository still names it.

#### B — Coffer's workspace root (the 2026-11-11 morning behaviour)

- **Lost because:** every turn without a directory shares it, so a task's
  output would be mixed with every channel turn's.

### What a run's files are kept as

#### A — Plain files in the task's folder, named by the prompt (chosen)

- **Good:** the agent already writes files; the prompt decides names
  (`reports/2026-11-11.md`) and whether it appends to one file, as Manus does.

#### B — An artifact directory per run, as GitHub Actions does

- **Lost because:** Coffer would invent per-run storage, retention and a
  per-run viewer for what an agent does by naming a file; reconsidered only if
  several real tasks need files tied to a single run.

### Sending a report as a file

`coffer channel notify` (`POST /channels/{uid}/notify`) gains `files`, absolute
paths sent after the text by the same upload path a channel reply's files use.
`coffer__channel_notify` already took `files`; the CLI and the Send-test
route now match it. No other path was considered: building a second upload
would duplicate the reply-files rules (size caps, photo vs document, a failed
upload named instead of dropped).

## Decision

A task's prompt is `PROMPT.md` in its own folder,
`~/.coffer/content/workspace/scheduled-tasks/<uid>/`, never in its config;
every run works in that folder (a task names no directory, see History); a run's files are plain files
there, named by the prompt; notify can send files.

Rules a change must keep:

- **The folder is named by uid**, like every resource file since O-10, so a
  rename moves nothing.
- **The file is the truth.** A run reads `PROMPT.md` as it is when the run
  starts; a missing or empty file fails the run with that reason. The page
  writes it through `PUT /scheduled-tasks/{uid}/prompt`; creating a task
  writes it.
- **No prompt in the config.** A config carrying one is refused on every path;
  only `POST /scheduled-tasks` accepts a prompt (top-level, or inside `config`
  for older callers) and moves it into the file.
- **Content, not synced.** The folder is under `content/`, the user's only copy,
  like the workspace. Deleting a task leaves its folder: what it wrote is the
  owner's.
- **One place on the page.** The Files tab shows the whole folder as a
  skill's folder is shown: the prompt, scripts it runs, intermediate files and
  reports. `PROMPT.md` opens first and is the one file editable there; others
  are changed on disk. There is no separate Prompt tab (see History).

## Consequences

- Tasks written before 2026-11-11 have their prompt moved into `PROMPT.md`
  when the daemon starts (an existing file wins), then dropped from the config.
- The Edit dialog no longer shows the prompt; New task still asks for it, and
  the Files tab edits it afterwards.
- `coffer task prompt` replaces the file and `coffer task files` lists the
  folder; `coffer task show` returns `prompt` and `folder`.
- A deleted task's folder stays until the owner removes it.

## History

- 2026-11-11, later the same day: the separate Prompt tab was removed. The
  owner found the Prompt and Files cards too small and asked whether the
  Prompt tab was needed at all, since a task also keeps scripts, intermediate
  files and results that "都应该在文件里展示". Options: keep a Prompt tab
  beside Files (two places show the same file), or fold it into Files with
  `PROMPT.md` open first and editable (chosen, as Claude Code's scheduled tasks
  keep the prompt as one file in the task's folder). The Files card now
  reaches the bottom of the window like every file browser.
- 2026-11-11 evening: a task names no directory any more, and is created
  without its prompt. The owner asked "新建任务的时候不应该支持选目录，直接就使用内部目录是不是更合理？"
  and "提示词也不用先填吧". Options for the directory, put to the owner on a
  card: drop it from New task only and keep it in Edit (for a task that must
  start in a repository, as the dev follow-up does), or drop it everywhere and
  let a prompt that needs another directory say so (chosen by the owner, the
  lean answer: the agent can `cd` itself). Every run now works in the task's
  folder; a `cwd` in a config is refused, and one written earlier is dropped
  at startup. Lost: a run no longer starts where a repository's `AGENTS.md`
  would load by itself, so such a prompt has to point the agent at it. A task
  created without a prompt gets an empty `PROMPT.md`, must be named, and is
  created paused; at the owner's word ("必须有提示词才能开始运行") Resume and
  Run now are refused while the file is empty. A file emptied by hand later
  still fails the run that finds it so.
