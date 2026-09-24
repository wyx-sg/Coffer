# Agent transcript history: how other products do it

**Feature**: browsing, searching and reusing the conversation history that coding agents store locally (Claude Code's `~/.claude/projects/<project>/<session>.jsonl`, Codex's `~/.codex/sessions` rollouts), across agents and fast even with thousands of sessions · **Coffer spec**: [agent-registry](../../openspec/specs/agent-registry/spec.md) · **Related ADRs**: [writing-agent-native-config-safely](../decisions/writing-agent-native-config-safely.md), [agent-descriptor-manifest](../decisions/agent-descriptor-manifest.md)
**Researched**: 2026-09 · **Method**: web research, primary sources (official docs, repository source read through the GitHub API, and record shapes observed in transcripts written by Claude Code 2.1.280–2.1.281 and Codex in September 2026). Star counts are from the GitHub API on 2026-09-24.

---

## Scope and the frame used

A transcript-history feature has five parts, and every product below is described along them:

1. **Source format**: what the agent writes on disk, how stable it is, and how it records subagents, compaction, titles and forks.
2. **Parsing**: how a reader turns records into conversational turns, and what it does with lines it doesn't recognise.
3. **Listing and indexing**: how a list of thousands of sessions comes back fast. Options include head/tail reads, mtime/size caches, SQLite FTS and Tantivy.
4. **Privacy**: transcripts hold every pasted key and every `cat .env`. The question is whether anything is detected, redacted or kept out of the index.
5. **Reuse**: resume, fork, export, and cross-agent hand-off.

| Product | Kind | Stars (2026-09) |
| --- | --- | --- |
| [anthropics/claude-code](https://github.com/anthropics/claude-code) | The agent (writes JSONL transcripts) | 147.9k |
| [farion1231/cc-switch](https://github.com/farion1231/cc-switch) | Desktop all-in-one for CLI agents; Session Manager | 136.4k |
| [openai/codex](https://github.com/openai/codex) | The agent (writes rollout JSONL plus a SQLite state DB) | 126.3k |
| [slopus/happy](https://github.com/slopus/happy) | Mobile/web client for Claude Code and Codex | 23.9k |
| [winfunc/opcode](https://github.com/winfunc/opcode) (formerly Claudia) | Claude Code GUI | 22.4k |
| [ccusage/ccusage](https://github.com/ccusage/ccusage) | Usage/cost parser over transcripts | 18.7k |
| [siteboon/claudecodeui](https://github.com/siteboon/claudecodeui) (CloudCLI) | Web UI for several CLI agents | 13.8k |
| [kenn-io/agentsview](https://github.com/kenn-io/agentsview) | Cross-agent session archive and search | 6.0k |
| [harbor-framework/harbor](https://github.com/harbor-framework/harbor) | Eval framework; owns the ATIF trajectory format | ~5.6k |
| [entireio/cli](https://github.com/entireio/cli) | Captures sessions into git alongside commits | 5.1k |
| [stravu/crystal](https://github.com/stravu/crystal) (now Nimbalyst) | Parallel-worktree agent runner | 3.1k |
| [jhlee0409/claude-code-history-viewer](https://github.com/jhlee0409/claude-code-history-viewer) | Desktop history viewer, ~30 agents | 2.2k |
| [specstoryai/getspecstory](https://github.com/specstoryai/getspecstory) | SpecStory CLI: saves chat history into `.specstory/` | 1.3k |
| [d-kimuson/claude-code-viewer](https://github.com/d-kimuson/claude-code-viewer) | Web client and viewer for Claude Code | 1.3k |
| [daaain/claude-code-log](https://github.com/daaain/claude-code-log) | JSONL → HTML/Markdown converter plus TUI | 1.2k |
| [letta-ai/agent-file](https://github.com/letta-ai/agent-file) | `.af` agent serialisation format | ~1.2k |
| [Dicklesworthstone/coding_agent_session_search](https://github.com/Dicklesworthstone/coding_agent_session_search) ("cass") | Cross-agent search CLI/TUI | 1.1k |
| [ctxrs/ctx](https://github.com/ctxrs/ctx) | Cross-agent search plus "blame for agent sessions" | 1.1k |
| [vshulcz/deja-vu](https://github.com/vshulcz/deja-vu) | Memory built from on-disk history of 34 agents | 1.0k |
| [jazzyalex/agent-sessions](https://github.com/jazzyalex/agent-sessions) | macOS session browser, 16 agents | 0.9k |
| [ZeroSumQuant/claude-conversation-extractor](https://github.com/ZeroSumQuant/claude-conversation-extractor) | Exporter/search | 0.7k |
| [loocor/codmate](https://github.com/loocor/codmate) | macOS session manager (Codex, Claude, Gemini) | 0.7k |
| [thomas-pedersen/cursor-chat-browser](https://github.com/thomas-pedersen/cursor-chat-browser) | Cursor chat browser | 0.5k |
| [raine/claude-history](https://github.com/raine/claude-history) | Fuzzy-search TUI for Claude Code | 0.5k |
| [jerrywu001/cc-sessions-viewer](https://github.com/jerrywu001/cc-sessions-viewer) | Chinese-ecosystem multi-agent viewer | 0.4k |
| [letta-ai/trajectory](https://github.com/letta-ai/trajectory) | Cross-agent transcript normaliser | ~0.26k |
| [Nwflower/dsh-chat-import](https://github.com/Nwflower/dsh-chat-import) | Imports 25+ agents' history into DeepSeek Harness | 0.2k |
| [S2thend/cursor-history](https://github.com/S2thend/cursor-history) | Cursor history CLI/library/MCP | 0.2k |
| [eckardt/cchistory](https://github.com/eckardt/cchistory) | Shell-command history mined from transcripts | 0.1k |

Cursor's IDE chat, OpenTelemetry's GenAI conventions and the Agent Trace spec have no star count and are covered in their own sections.

---

## 1. The source formats

### 1.1 Claude Code: one JSONL per session, a parent-pointer tree inside

**Location and naming.** Transcripts live at `~/.claude/projects/<project>/<session-id>.jsonl`. `<project>` is the working directory with every non-alphanumeric character replaced by `-`. A name longer than 200 characters is truncated and suffixed with a hash of the full path ([sessions docs, "Where transcripts are stored"](https://code.claude.com/docs/en/sessions#where-transcripts-are-stored)).
- The encoding is lossy: `/`, `_`, `.` and `-` all become `-`. Every serious reader takes the real project path from the `cwd` field inside the file instead of decoding the directory name. opcode marks its own `replace('-','/')` decoder as deprecated for this reason ([claude.rs](https://github.com/winfunc/opcode/blob/main/src-tauri/src/commands/claude.rs)).
- `CLAUDE_CONFIG_DIR` moves the whole tree. `CLAUDE_CODE_PROJECT_DIR_NAME` (v2.1.234+) lets an embedding host pin the `<project>` name ([sessions docs](https://code.claude.com/docs/en/sessions#name-the-project-directory-yourself)).

**Sidecars next to each session** ([`.claude` directory docs](https://code.claude.com/docs/en/claude-directory)):
- `<session>/subagents/agent-<id>.jsonl` holds the subagent transcripts. Each has a `agent-<id>.meta.json` beside it; observed fields are `agentType`, `description`, `toolUseId` (the spawning `Agent`/Task call), `spawnDepth`, `requestShape`. Older versions wrote `agent-<id>.jsonl` flat in the project directory, which is why most readers still skip any `agent-*` file at the top level.
- `<session>/tool-results/` holds large tool outputs spilled out of the transcript.
- `<session>.orphaned-<ts>-<suffix>.jsonl` and `<session>.jsonl.superseded-<ts>` are earlier transcripts for the same session that Claude Code set aside instead of overwriting. A reader that globs `*.jsonl` without care will pick up the orphaned form as a duplicate session.
- `~/.claude/history.jsonl` is a separate log of every typed prompt (`display`, `pastedContents`, `project`, `sessionId`, `timestamp`), used for up-arrow recall and kept until deleted. claudecodeui uses it as a title source.
- `~/.claude/file-history/<session>/` keeps pre-edit file snapshots for checkpoint restore (last 100 checkpoints).

**Retention.** A sweep deletes transcripts, subagent and tool-result sidecars, file-history and several caches once they are older than `cleanupPeriodDays`. The default is **30 days** and the minimum 1; `0` is a validation error. The sweep pauses if it can't determine the retention period safely, and doesn't run in `--bare` mode. `claude project purge` deletes one project's transcripts, auto memory, tasks/debug/file-history and its `history.jsonl` lines. Auto memory under `projects/<p>/memory/` is not swept ([`.claude` directory docs](https://code.claude.com/docs/en/claude-directory)). A browser over Claude Code history therefore sees a rolling 30-day window by default, not "all history".

**Stability.** The vendor says outright that "the entry format is internal to Claude Code and changes between versions, so scripts that parse these files directly can break on any release". It points script authors at `/export`, `claude -p --output-format json`, the `transcript_path` field given to hooks, or the Agent SDK instead ([sessions docs](https://code.claude.com/docs/en/sessions#where-transcripts-are-stored)).

**Record types.** Each line is a JSON object with a `type`. The types seen in September 2026 transcripts:
- **Conversation**: `user`, `assistant`, `system`, `attachment`. Each carries `uuid`, `parentUuid`, `sessionId`, `timestamp`, `cwd`, `gitBranch`, `version`, `isSidechain`, `userType` and `entrypoint`.
- **Metadata**: `ai-title`, `custom-title`, `agent-name`, `last-prompt`, `mode`, `permission-mode`, `pr-link`, `queue-operation`, `bridge-session`, `cost-state`, `file-history-snapshot`, `file-history-delta`, `atis-latch`. Most carry only `sessionId` plus their payload, with no `uuid`.
- **Older types** still in the wild: `summary` (with `leafUuid`) and `tag`. Open-source schemas list more (`progress`, `agent-setting`); [claude-code-viewer's Zod schemas](https://github.com/d-kimuson/claude-code-viewer/tree/main/src/lib/conversation-schema) have one file per type.
- In the sample observed, metadata and attachment lines outnumbered `user`+`assistant` lines. A reader that assumes "one line = one message" is wrong by a wide margin.

**Flags that change the meaning of a turn:**
- **`isMeta: true`** marks user-role lines written by the harness (skill bodies, caveats) rather than the person.
- **`isCompactSummary: true`** marks the synthetic user turn that carries a compaction summary.
- **`isSidechain: true`** marks subagent lines.
- **`isVisibleInTranscriptOnly`** and **`toolUseResult`** mark tool plumbing.
- A `type:"user"` line whose content is only `tool_result` blocks is tool output, not a human turn. cc-switch relabels these as role `tool` ([claude.rs](https://github.com/farion1231/cc-switch/blob/main/src-tauri/src/session_manager/providers/claude.rs)).
- Human-typed text is also wrapped with harness markup: `<command-name>`, `<command-message>`, `<command-args>`, `<local-command-stdout>`, `<local-command-caveat>`, system-reminder blocks, `<ide_selection>`, `<ide_opened_file>`, "Caveat: The messages below were generated…", `[Request interrupted by user]`.

**Compaction.** `/compact` or auto-compaction writes a `system` line with `subtype: "compact_boundary"`. Observed fields: `compactMetadata {trigger, preTokens, postTokens, durationMs, preservedSegment, preservedMessages}` and a `logicalParentUuid`, with `parentUuid: null`. After it comes an `isCompactSummary` user turn. The physical parent chain restarts at the boundary, and `logicalParentUuid` points at the pre-compaction history, possibly in an earlier file. claude-code-history-viewer follows it up to 50 hops so a conversation that continued in a new file reads as one ([chain.rs](https://github.com/jhlee0409/claude-code-history-viewer/blob/main/src-tauri/src/commands/session/chain.rs)).

**Titles.** An unnamed session gets an `ai-title` line, written by a background small-model call summarising the first prompt. A `/rename`, `-n`, or `rename_session()` call appends a `custom-title` line; the latest wins. Accepting a plan replaces the title ([sessions docs, "Name your sessions"](https://code.claude.com/docs/en/sessions#name-your-sessions)). Titles are append-only records in the transcript itself, not a separate index.

**The vendor's own reference reader.** The Agent SDK ships `list_sessions()`, `get_session_info()`, `get_session_messages()`, `list_subagents()`, `get_subagent_messages()`, `rename_session()` and `tag_session()` ([Python SDK reference](https://code.claude.com/docs/en/agent-sdk/python)). Its implementation, [`_internal/sessions.py`](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/_internal/sessions.py), is the most authoritative description of how to read the format:
- **Listing without parsing.** It stats each file and reads only the **first and last 64 KiB** (`LITE_READ_BUF_SIZE = 65536`). It pulls fields out with string search, not JSON parsing:
  - title: `customTitle` → `aiTitle` → `lastPrompt` → `summary`, searched in the tail then the head;
  - `gitBranch` from the tail, `cwd` and the first `timestamp` from the head;
  - the tag from `{"type":"tag"` lines in the tail;
  - a file whose first line has `isSidechain:true` is dropped.
- **First prompt.** It skips `tool_result` lines, `isMeta`, `isCompactSummary`, and text matching a skip pattern (`<local-command-stdout>`, `<session-start-hook>`, `<tick>`, `<goal>`, `[Request interrupted by user…]`, a lone `<ide_opened_file>` or `<ide_selection>`). A `<command-name>` turn is kept only as a fallback.
- **Duplicates.** Rows are deduplicated by session ID, keeping the newest mtime.
- **Reading one session.** It keeps only lines with a `uuid` of type user/assistant/progress/system/attachment, silently skipping corrupt lines. It then finds terminal entries (nothing points to them), walks back to the nearest user/assistant leaf, and prefers the latest non-sidechain, non-meta, non-team leaf. From there it walks `parentUuid` to the root and reverses.
- **Deliberately not followed.** It does **not** follow `logicalParentUuid`, "matching VS Code IDE behaviour": the compact summary stands in for what it replaced.
- **What a reader sees.** Visible messages exclude `isMeta` and sidechain lines but *include* compact summaries, "the only representation of that content post-compaction".

Because a transcript is a tree, walking file order instead of `parentUuid` from the right leaf shows abandoned branches (from rewind or edit-and-resend) as if they were the live conversation.

### 1.2 Codex: rollout JSONL, a session-name index, and SQLite projections

**Layout.** Rollouts live at `~/.codex/sessions/YYYY/MM/DD/rollout-<timestamp>-<thread-id>.jsonl`. Archived ones move to `~/.codex/archived_sessions/`. A reverted thread keeps its thread ID but gets a new immutable file, `rollout-<ts>-<thread-id>_<rollout-id>.jsonl` ([rollout_file_name.rs](https://github.com/openai/codex/blob/main/codex-rs/rollout/src/rollout_file_name.rs), [metadata.rs](https://github.com/openai/codex/blob/main/codex-rs/rollout/src/metadata.rs)). Because the date is in the path, "newest first by creation" is a reverse directory walk with no file opened.

**Records.** Each line is `{timestamp, ordinal, type, payload}` ([lib.rs `decode_rollout_line`](https://github.com/openai/codex/blob/main/codex-rs/rollout/src/lib.rs)). The types:
- **`session_meta`**: the first line. Observed payload keys: `id`, `cwd`, `cli_version`, `originator`, `source`, `model_provider`, `git`, `base_instructions`, `forked_from_id`, `parent_thread_id`, `agent_nickname`, `history_mode`, `history_base`, `subagent_history_start_ordinal`, `thread_source`, `dynamic_tools`, `context_window`.
- **`response_item`**: the model-level items. Subtypes include `message`, `reasoning`, `function_call`, `function_call_output`, `custom_tool_call`, `tool_search_call`, `web_search_call`.
- **`event_msg`**: UI-level events. Subtypes include `item_completed`, `token_count`, `task_started`, `task_complete`, `turn_aborted`, `thread_settings_applied`.
- **Also**: `turn_context`, `compacted` (compaction), `world_state`, `token_usage_record`.

[policy.rs](https://github.com/openai/codex/blob/main/codex-rs/rollout/src/policy.rs) decides which items are persisted at all. A thread's `history_mode` is `Legacy` (event-only rollouts) or `Paginated` (persists canonical `ItemCompleted(TurnItem)` records) ([ordinal.rs](https://github.com/openai/codex/blob/main/codex-rs/rollout/src/ordinal.rs)). The format has therefore changed shape inside one product, and `codex migrate-rollouts [--apply] [--thread ID] [--max-mib-per-second N]` exists to convert old sessions ([cli main.rs](https://github.com/openai/codex/blob/main/codex-rs/cli/src/main.rs), [migrate_rollouts.rs](https://github.com/openai/codex/blob/main/codex-rs/cli/src/migrate_rollouts.rs)).

**Compression.** A background worker zstd-compresses (level 3) rollouts older than **7 days** into `.jsonl.zst`. It runs at most 2 jobs, holds a run-marker lock, writes to a temp file, verifies the result, then renames it over the original ([compression.rs](https://github.com/openai/codex/blob/main/codex-rs/rollout/src/compression.rs)). The reader opens either form transparently and retries briefly if the file vanishes mid-transition. A cross-process `rollout-maintenance.lock` stops compression and migration from renaming over the same file at once ([maintenance.rs](https://github.com/openai/codex/blob/main/codex-rs/rollout/src/maintenance.rs)). A third-party reader that globs only `*.jsonl` silently loses every session older than a week.

**Titles.** `~/.codex/session_index.jsonl` is an append-only log of `{id, thread_name, updated_at}`; the newest entry wins and readers scan from the end ([session_index.rs](https://github.com/openai/codex/blob/main/codex-rs/rollout/src/session_index.rs), with a [reverse JSONL scanner](https://github.com/openai/codex/blob/main/codex-rs/rollout/src/reverse_jsonl_scanner.rs)).

**SQLite state DB.** `state_<n>.sqlite` (location from `sqlite_home` / `CODEX_SQLITE_HOME`, per the [config reference](https://learn.chatgpt.com/docs/config-file/config-reference)) is a derived metadata index. Tables observed include:
- `threads(id, rollout_path, created_at, updated_at, source, model_provider, cwd, title, …, has_user_event)`;
- `thread_spawn_edges(parent_thread_id, child_thread_id, status)`;
- `projects`/`project_roots`, `backfill_state`, `rollout_migration_state`.

At startup Codex backfills the DB from rollouts, and it falls back to scanning files and "repairs" `rollout_path` when the DB is stale ([state_db.rs](https://github.com/openai/codex/blob/main/codex-rs/rollout/src/state_db.rs)). A separate `thread_history_<n>.sqlite` holds `thread_turns`/`thread_items` with `rollout_byte_offset` and a `thread_history_projection_state(next_rollout_byte_offset, next_rollout_ordinal)` cursor. That is a projection built incrementally from the JSONL by byte offset, "stateless … without reconstructing earlier history" ([thread_history_projection.rs](https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/src/protocol/thread_history_projection.rs)). The JSONL stays canonical; SQLite is an index Codex can rebuild.

**Codex's own listing** ([list.rs](https://github.com/openai/codex/blob/main/codex-rs/rollout/src/list.rs)):
- It reads at most the first 10 records of each file for the summary.
- It scans at most 10,000 files per request, returning `reached_scan_cap` and an opaque `(timestamp, id)` cursor so paging stays stable while new files appear.
- It filters by source (interactive CLI/VS Code by default), provider and cwd.
- Sorting by created-at walks directories newest-first. Sorting by updated-at has to stat everything up to the cap, because updated-at isn't in the filename.

**Codex's own search.** It shells out to **ripgrep** over the sessions directory with the JSON-escaped term, then scans `.zst` files in-process. With no ripgrep it falls back to a Rust scan ([search.rs](https://github.com/openai/codex/blob/main/codex-rs/rollout/src/search.rs)).

**Secret concerns.** Codex's `history.jsonl` (prompt history) can be switched off with `history.persistence` and capped with `history.max_bytes` ([config reference](https://learn.chatgpt.com/docs/config-file/config-reference)). No redaction of rollout content was found. A comment in the app server calls its resume-response trimming of large MCP and image payloads a "temporary bandaid", applied to the response only ([thread_resume_redaction.rs](https://github.com/openai/codex/blob/main/codex-rs/app-server/src/request_processors/thread_resume_redaction.rs)).

**Scale.** On one working developer machine: 1,941 Codex rollouts totalling about 2 GB, the largest a single 323 MB file. Claude Code's 30-day window held 162 top-level transcripts totalling about 550 MB, the largest 61 MB. cc-sessions-viewer added a 64 MB cap to its text cache after a user's 1.9 GB Codex corpus pinned memory (see §4.7). "Load the file" is not a plan; "read the head and tail" is.

### 1.3 Cursor: SQLite key-value blobs that keep moving

Cursor keeps IDE chat in VS Code-style `state.vscdb` SQLite files. The most thorough public description is SpecStory's [CURSORIDE-FORMAT.md](https://github.com/specstoryai/getspecstory/blob/dev/specstory-cli/pkg/providers/cursoride/CURSORIDE-FORMAT.md):
- **Where conversations live.** The global `cursorDiskKV` table holds `composerData:<id>` headers (`name`, `_v`, `fullConversationHeadersOnly[]`, `createdAt`, `lastUpdatedAt`, `workspaceIdentifier`). Each message is its own row, `bubbleId:<composerId>:<bubbleId>` (`type` 1=user, 2=assistant, `text`, `thinking`, `toolFormerData`).
- **Drift, chat storage.** Old Cursor kept chat in per-workspace `ItemTable['workbench.panel.aichat.view.aichat.chatdata']`. Tool data moved from `capabilities[].data.bubbleDataMap` (sometimes a JSON string) to inline `toolFormerData` at `_v` 3.
- **Drift, chat-to-workspace mapping.** It moved from `composer.composerData.allComposers` (Cursor 2) to `selectedComposerIds`, which under-reports (Cursor 3). From Cursor 3.12 it is only `composerData.workspaceIdentifier`, so the reader has to scan every header.
- **Workspace IDs** are `md5(path + birthtime-or-inode salt)`.
- **Reading safely.** Readers must open the DB in WAL mode and watch the `-wal` file, because that is where most writes land.
- **Other stores.** The Cursor CLI writes separate per-session `store.db` files and JSONL `agent-transcripts`.

The export tools show what that drift costs. [somogyijanos/cursor-chat-export](https://github.com/somogyijanos/cursor-chat-export) (246★, last push 2024-08) queries only the legacy `ItemTable` key, and its open issues ask "Is this still working for anyone?". [cursor-chat-browser](https://github.com/thomas-pedersen/cursor-chat-browser/blob/main/src/app/api/workspaces/route.ts) full-scans `cursorDiskKV LIKE 'composerData:%'` / `'bubbleId:%'` and guesses a chat's workspace from file paths mentioned in it. [cursor-history](https://github.com/S2thend/cursor-history) merges four Cursor sources with per-record provenance, adds backup/restore and workspace migration, and ships a written compatibility contract.

---

## 2. What the agents themselves offer

### 2.1 Claude Code: `/resume`, `--continue`, `/branch`, `--fork-session`

From the [sessions docs](https://code.claude.com/docs/en/sessions):
- **Entry points.**
  - `claude --continue` reopens the latest session in this directory. It skips `-p`, SDK and `/loop`-first sessions unless run as `claude -p --continue`.
  - `claude --resume` opens the picker. `claude --resume <name|id|transcript-path>` resumes directly.
  - `claude --from-pr <n|url>` filters to sessions linked to a PR. `pr-link` records are written when Claude creates the PR.
- **Cross-project lookup by ID** (v2.1.223+). Claude Code looks in the current project and its worktrees, then in every other project. It resolves only when exactly one other project holds a transcript for that ID, so a hand-copied duplicate yields not-found rather than an arbitrary copy.
- **The picker.**
  - Scope is the current worktree by default. `Ctrl+W` widens to all worktrees, `Ctrl+A` to all projects, and `Ctrl+B` filters to the current branch.
  - Typing searches, and a pasted PR URL finds the session that created it.
  - `Space` previews and `Ctrl+R` renames.
  - Each row shows the name, AI title, summary or first prompt, plus time since last activity, git branch and **file size**.
  - Multiple entries for one session are grouped.
  - Picking a session from an unrelated project copies a `cd … && claude --resume …` command to the clipboard instead of switching directory.
- **What resume restores.** Full history including tool calls; the model (unless it has been retired or overridden); the agent; the permission mode (terminal paths only, with a table of exceptions, e.g. `bypassPermissions` is never silently restored); an active goal; unexpired scheduled tasks. It does **not** restore `--mcp-config`, `--settings`, `--plugin-dir` or `--add-dir`. A tool that was running at a crash does not re-run.
- **Resume from a summary.** On Pro/Max, resuming a session idle for more than about an hour and over 100k tokens offers "resume from summary" (runs `/compact` first), "resume as-is", or "don't ask again", because the prompt cache has expired.
- **Branching.** `/branch [name]`, or `--continue/--resume --fork-session`, copies the transcript up to that point into a new session ID and leaves the original unchanged. In-process `/branch` keeps session permission grants, running background tasks and Remote Control; `--fork-session` in a new process does not. Resuming one session in two terminals *without* forking interleaves both into one transcript.
- **Export.** `/export` renders plain text to the clipboard or a file.

The Agent SDK adds programmatic `resume` / `fork_session` / `continue`. It also offers a `SessionStore` adapter that mirrors transcripts to your own backend (examples for Postgres, Redis, S3) so another host can resume ([SDK sessions guide](https://code.claude.com/docs/en/agent-sdk/sessions), [session_stores examples](https://github.com/anthropics/claude-agent-sdk-python/tree/main/examples/session_stores)). The guide's own advice for cross-host continuity is often *not* to ship transcripts: "capture the results you need … as application state and pass them into a fresh session's prompt."

### 2.2 Codex: `resume`, `fork`, `archive`, `delete`

From [cli main.rs](https://github.com/openai/codex/blob/main/codex-rs/cli/src/main.rs):
- **`codex resume [SESSION_ID|name]`** opens a picker by default. `--last` skips the picker, `--all` disables cwd filtering and adds a CWD column, and `--include-non-interactive` adds exec sessions. "UUIDs take precedence if it parses."
- **`codex fork [SESSION_ID]`** works the same way and creates a new thread whose `session_meta.forked_from_id` points at the source. A fork records a logical fork cutoff so a revert's history base is not mistaken for its parent ([metadata.rs](https://github.com/openai/codex/blob/main/codex-rs/rollout/src/metadata.rs)).
- **`codex archive` / `unarchive` / `delete`** take an ID or name; `delete --force` requires a UUID. Archiving moves the rollout to `archived_sessions/`.
- **`codex exec resume`** exists for non-interactive runs.
- **Resume hints** print `codex resume <name>`, preferring the name over the ID and inserting `--` when the name starts with `-` ([resume_command.rs](https://github.com/openai/codex/blob/main/codex-rs/utils/cli/src/resume_command.rs)).

**A unified-list trap.** Codex's picker filters by the `model_provider` recorded in each session header. Sessions made through a third-party provider therefore vanish from the default list after switching back. cc-switch documents rewriting that tag (with backups) to unify the list ([guide](https://github.com/farion1231/cc-switch/blob/main/docs/guides/codex-unified-session-history-guide-en.md)). A cross-agent browser that shows "all sessions" regardless of provider sidesteps this. A tool that edits the headers to achieve the same is writing into the agent's state.

---

## 3. Single-agent readers and exporters (Claude Code)

### 3.1 ccusage: usage parsing at scale, with no cache

ccusage moved from TypeScript to a native Rust binary in May 2026 and now reads 20 agents.
- **Discovery.** `CLAUDE_CONFIG_DIR` may be a comma-separated list. If unset, ccusage reads **both** `~/.config/claude` and `~/.claude` ([paths.rs](https://github.com/ccusage/ccusage/blob/main/rust/adapters/claude/src/paths.rs)).
- **Walk.** It walks `projects/` recursively, so it picks up `subagents/` files and attributes each to its parent session.
- **Fast filtering.** A `memmem` prefilter skips any line without `"usage":{` before JSON parsing. Surviving lines are deserialised into a typed struct. Lenient helpers coerce wrongly-typed fields to 0/None instead of dropping the line, and unparseable lines are skipped silently ([lib.rs](https://github.com/ccusage/ccusage/blob/main/rust/adapters/claude/src/lib.rs), [jsonl.rs](https://github.com/ccusage/ccusage/blob/main/rust/adapters/common/src/jsonl.rs)).
- **Dedup key.** It hashes `message.id + requestId`, because Claude Code copies the same response into several session files. The session ID is added only when `requestId` is missing. On a collision, a non-sidechain copy beats a sidechain copy. A second message-ID-only index catches sidechain replays that carry new request IDs ([README](https://github.com/ccusage/ccusage/blob/main/rust/adapters/claude/src/README.md)).
- **Speed.** Every run re-reads everything. It is fast because files are split across cores in chunks balanced by size.
- **Codex.** It reads `event_msg/token_count` from `sessions/` and `archived_sessions/`. It prefers the per-turn `last_token_usage`, but only when the cumulative total actually changed, since Codex writes repeated identical events. The model comes from the latest `turn_context`. It skips the parent-history prefix that a subagent rollout replays ([codex README](https://github.com/ccusage/ccusage/blob/main/rust/adapters/codex/src/README.md)).

### 3.2 claude-code-log: the most thorough subagent and dedup handling

- **Parsing.** Pydantic models cover the known types. An unknown type that has `uuid` and `sessionId` becomes a `PassthroughTranscriptEntry` so the parent chain isn't broken. Other unknown types print one warning per type per file ([converter.py](https://github.com/daaain/claude-code-log/blob/main/claude_code_log/converter.py), [models.py](https://github.com/daaain/claude-code-log/blob/main/claude_code_log/models.py)).
- **Ordering.** Messages are ordered as a DAG from `parentUuid` ([dag.py](https://github.com/daaain/claude-code-log/blob/main/claude_code_log/dag.py)).
- **Duplicates.** Deduplication merges copies written during a Claude Code upgrade and re-points orphaned children at the survivor.
- **Subagents.** It finds each subagent file by `agentId`, in the old flat layout or the new `subagents/` directory. It links nested spawns through the `.meta.json` `toolUseId`, falls back to hashing the Task prompt, and splices the subagent's messages under the Task call that spawned them.
- **Harness markup.** Command, stdout and reminder blocks become typed message kinds rather than being dropped ([user_factory.py](https://github.com/daaain/claude-code-log/blob/main/claude_code_log/factories/user_factory.py)). Compaction is detected by the summary text prefix, not the `isCompactSummary` flag.
- **Cache.** SQLite with 14 migrations, entries stored zlib-compressed. Freshness = mtime within 1 s *and* size, plus a fingerprint of the `subagents/` directory. It refreshes incrementally on append ([cache.py](https://github.com/daaain/claude-code-log/blob/main/claude_code_log/cache.py)). By default the DB sits **inside** `~/.claude/projects/`.
- **Search.** A contentless FTS5 index: about 20% extra size instead of 84%; `CROSS JOIN` needed when filtering (2.4 ms vs 2 s); base64 images kept out ([search.py](https://github.com/daaain/claude-code-log/blob/main/claude_code_log/search.py)).
- **Output and resume.** Paginated HTML, Markdown, JSON, served from a loopback server with a Host-header check. The TUI resumes with `exec claude -r <id>`.

### 3.3 claude-code-history-viewer: incremental offsets and windowed loading

- **Stack.** Tauri 2 with a Rust backend and React 19 frontend, covering about 30 agents ([providers/](https://github.com/jhlee0409/claude-code-history-viewer/tree/main/src-tauri/src/providers)).
- **Project scan.** The real project path comes from the decoded name if it exists on disk, else the `cwd` of the newest file. Message counts are estimated from file size, not parsed.
- **Cache.** A per-project `.session_cache.json` (again inside Claude's directory) holds mtime, size and **last byte offset read**, so appends are read incrementally with `seek` ([load.rs](https://github.com/jhlee0409/claude-code-history-viewer/blob/main/src-tauri/src/commands/session/load.rs)).
- **Opening a session.** The file is mmapped; line starts are found with memchr; lines are parsed in parallel with simd-json and restored to order. `load_session_messages_paginated(offset, limit, exclude_sidechain)` feeds a virtualised list.
- **Search.** Parallel Aho-Corasick over raw files, with a 64-query LRU keyed by each file's (size, mtime) ([search.rs](https://github.com/jhlee0409/claude-code-history-viewer/blob/main/src-tauri/src/commands/session/search.rs)).
- **Resume.** Only allowlisted command shapes are accepted, then opened in the platform's terminal ([resume.rs](https://github.com/jhlee0409/claude-code-history-viewer/blob/main/src-tauri/src/commands/session/resume.rs)).

### 3.4 claude-code-viewer: an FTS5 trigram index and an SDK-driven resume

- **Parsing.** Zod schemas, one per record type. A line that fails JSON or schema validation becomes an `{type:"x-error", line, lineNumber}` placeholder: **kept and flagged, not dropped** ([parseJsonl.ts](https://github.com/d-kimuson/claude-code-viewer/blob/main/src/server/core/claude-code/functions/parseJsonl.ts)).
- **Cache.** SQLite via Drizzle at `~/.claude-code-viewer/cache.db`, outside the agent's directory. It is deleted and rebuilt if a migration fails ([DrizzleService.ts](https://github.com/d-kimuson/claude-code-viewer/blob/main/src/server/lib/db/DrizzleService.ts)).
- **Sync and search.** An mtime-driven sync fills `session_messages_fts` (FTS5, **trigram** tokenizer, so substring search works in any script). A file watcher pushes updates over SSE ([SyncService.ts](https://github.com/d-kimuson/claude-code-viewer/blob/main/src/server/core/sync/services/SyncService.ts)).
- **Title.** `custom-title` > `ai-title`, else the first valid user message, skipping Caveat text, "Warmup", `/clear`, `/login` and similar.
- **Resume.** It drives Claude Code through the Agent SDK's `query({resume})` and relays permission prompts ([ClaudeCode.ts](https://github.com/d-kimuson/claude-code-viewer/blob/main/src/server/core/claude-code/models/ClaudeCode.ts)).

### 3.5 Smaller tools

- **raine/claude-history.**
  - Cache: bincode per project in `~/.cache`, keyed by mtime and size and namespaced by a hash of `CLAUDE_CONFIG_DIR` ([cache.rs](https://github.com/raine/claude-history/blob/main/src/history/cache.rs)).
  - Search: weighted word-prefix scoring (title 5, project 4, summary 3, body 1, plus a recency bonus); quotes mean literal; a pasted UUID jumps straight to the session. Optional local fastembed semantic search.
  - It drops sessions that only contain `/clear`.
  - `Ctrl+R` resumes; `Ctrl+F` forks then resumes ([lexical.rs](https://github.com/raine/claude-history/blob/main/src/search/lexical.rs)).
- **claude-conversation-extractor.** A recursive `rglob` that treats subagent files as sessions. Titles strip all `<…>` tags. Four search modes: smart, exact, regex, and spaCy similarity. No index: every search scans ([extract_claude_logs.py](https://github.com/ZeroSumQuant/claude-conversation-extractor/blob/main/src/extract_claude_logs.py)).
- **cchistory.** Mines Bash tool calls and `!` commands out of transcripts into a `history`-style list. It pairs each `tool_use` with its `tool_result` to get the exit status and has a `--follow` tail mode ([jsonl-stream-parser.ts](https://github.com/eckardt/cchistory/blob/main/src/jsonl-stream-parser.ts)). It reconstructs project directory names by replacing only `/`, which is incomplete.

---

## 4. Cross-agent browsers and indexers

### 4.1 cc-switch Session Manager: stateless scan, head/tail read, frontend search

Shipped in v3.11.0 (2026-02-26), "browse and search conversation history for Claude Code, Codex, Gemini CLI, OpenCode, and OpenClaw". Later releases added batch delete, a directory picker for moved projects, a grouped view, Hermes (SQLite) and Grok Build ([CHANGELOG](https://github.com/farion1231/cc-switch/blob/main/CHANGELOG.md), [PRD](https://github.com/farion1231/cc-switch/blob/main/session-manager.md)).
- **Model.** `SessionMeta {provider_id, session_id, title, summary, project_dir, created_at, last_active_at, source_path, resume_command}` and `SessionMessage {role, content, ts}` ([mod.rs](https://github.com/farion1231/cc-switch/blob/main/src-tauri/src/session_manager/mod.rs)).
- **Scanning.** Eight provider scanners run in parallel threads. There is **no cache**; every refresh rescans.
- **Claude reader.** Files under 16 KB are read whole; otherwise it reads the first 10 lines plus the last 30 lines from a 16 KB tail ([utils.rs](https://github.com/farion1231/cc-switch/blob/main/src-tauri/src/session_manager/providers/utils.rs)). Head gives `sessionId`, `cwd`, start time and the first real prompt. Tail (read in reverse) gives last activity, `custom-title` and a 160-character summary.
- **Codex reader.** Reads `session_meta`, strips AGENTS.md and environment-context injections from the first user item, and skips subagent-sourced sessions. Titles come from `session_index.jsonl`, overridden by `state_5.sqlite threads.title`. The DB is opened read-only with a 2 s `busy_timeout`, and the "title differs from first message" comparison runs in SQL so the large blob never loads ([codex.rs](https://github.com/farion1231/cc-switch/blob/main/src-tauri/src/session_manager/providers/codex.rs)).
- **Search.** A frontend FlexSearch index over metadata only (ID, title, summary, project, path), not message bodies ([useSessionSearch.ts](https://github.com/farion1231/cc-switch/blob/main/src/hooks/useSessionSearch.ts)).
- **Resume.** `cd <escaped dir> && <resume command>` launched in the user's terminal of choice via osascript or each terminal's CLI; clipboard elsewhere ([terminal/mod.rs](https://github.com/farion1231/cc-switch/blob/main/src-tauri/src/session_manager/terminal/mod.rs)).
- **Delete.** cc-switch *does* write. It canonicalises the path, requires it to sit under a known provider root, checks the session ID matches, then removes the JSONL plus Claude's same-stem sidecar directory ([commands/session_manager.rs](https://github.com/farion1231/cc-switch/blob/main/src-tauri/src/commands/session_manager.rs)).

### 4.2 agentsview: a SQLite archive with byte-exact incremental sync

The most engineered indexer surveyed. Its SQLite database is *the archive*: it keeps sessions after the agent's retention sweep deletes the source, via `source_missing_at` ([schema.sql](https://github.com/kenn-io/agentsview/blob/main/internal/db/schema.sql), [storage.md](https://github.com/kenn-io/agentsview/blob/main/docs/agents/storage.md)).
- **Unified schema.**
  - `sessions`: about 90 columns, including agent, machine, cwd, git_branch, parent_session_id, relationship_type, transcript_fidelity, parser_malformed_lines, secret_leak_count and token/health stats.
  - `messages(session_id, ordinal UNIQUE, role, content, thinking_text, is_sidechain, is_compact_boundary, source_uuid, source_parent_uuid, …)`.
  - `tool_calls(…, subagent_session_id)`.
- **Search.** `messages_fts` is external-content FTS5 (`porter unicode61`) kept in sync by triggers, with a second CJK-tokenised table. Ranking combines FTS per session (best message via `ROW_NUMBER()`) with LIKE on title and first message ([db.go](https://github.com/kenn-io/agentsview/blob/main/internal/db/db.go), [search.go](https://github.com/kenn-io/agentsview/blob/main/internal/db/search.go)).
- **Provider interface.** `Discover, WatchPlan, Fingerprint, Parse, ParseIncremental, …`. A parse returns results *plus* per-source errors and a completeness flag, so one broken session in a multi-session store doesn't fail the rest ([provider.go](https://github.com/kenn-io/agentsview/blob/main/internal/parser/provider.go)).
- **Incremental sync** ([background-sync-efficiency.md](https://github.com/kenn-io/agentsview/blob/main/docs/internal/background-sync-efficiency.md)):
  - Skip on stat.
  - For append-only JSONL, persist inode/device, a committed byte offset that must sit just after a newline, a **128 KiB tail-anchor digest**, the parser cursor and a resumable SHA-256 of the prefix.
  - Resume an append only if the identity matches, the file only grew and the anchor still matches. The hash is extended over the new bytes only, so the cost is O(delta).
  - Anything else triggers a full reparse. A daily audit rehashes whole files to catch same-size rewrites.
- **Watching.** fsnotify (FSEvents on macOS), 500 ms batches, a 5 s minimum between callbacks, and overflow to a full-sync marker.
- **Format drift.**
  - A `dataVersion` integer is bumped on any parser change; an older DB is resynced without deleting orphaned sessions, and a DB from a newer version refuses to open.
  - A `parse-diff` tool compares incremental parses against full ones.
  - A 220 KB [session-format-sources.md](https://github.com/kenn-io/agentsview/blob/main/docs/internal/session-format-sources.md) pins upstream evidence per format.
- **Secrets.** A detector with "definite" vendor-anchored rules and "candidate" heuristics (entropy, JWT, basic-auth URLs). Only definite rules run inline during sync. Findings are stored with byte offsets and the rules version and used to redact search snippets. Raw content stays unless an `archive_content` policy narrows it ([secrets.go](https://github.com/kenn-io/agentsview/blob/main/internal/secrets/secrets.go)).

### 4.3 cass (coding_agent_session_search): normalised connectors and an agent-first CLI

- **Storage and index.** Canonical storage is SQLite (the author's pure-Rust frankensqlite). The lexical index is a derived Tantivy-family index carrying a `schema_hash.json`; a mismatch triggers a rebuild in scratch space and an atomic publish. Optional local MiniLM + HNSW semantic search is fused by RRF ([README](https://github.com/Dicklesworthstone/coding_agent_session_search/blob/main/README.md)).
- **Normalised schema** ([sqlite.rs](https://github.com/Dicklesworthstone/coding_agent_session_search/blob/main/src/storage/sqlite.rs)):
  - `conversations(agent, workspace, source, external_id, title, source_path, started_at, ended_at, …)`, UNIQUE `(source, agent, external_id)`;
  - `messages(conversation_id, idx, role, author, created_at, content, extra_json)`, UNIQUE `(conversation_id, idx)`, written with `INSERT OR IGNORE`;
  - `snippets(file_path, start_line, end_line, …)`;
  - a `sources` table for remote machines.
- **Connectors.** About 40 connectors in a separate crate share `NormalizedConversation / NormalizedMessage / NormalizedInvocation` types ([types.rs](https://github.com/Dicklesworthstone/franken_agent_detection/blob/main/src/types.rs)).
- **Freshness.** A watcher with a 2 s debounce, plus "stale on read": an index older than 30 minutes spawns a niced background reindex behind a lock. Optional launchd/systemd schedules are available.
- **Ranking.** BM25 blended with recency, 0.7 recency by default.
- **Robot mode.** Aimed at agents calling it ([ROBOT_MODE.md](https://github.com/Dicklesworthstone/coding_agent_session_search/blob/main/docs/ROBOT_MODE.md)):
  - `--robot --fields minimal --max-tokens N --cursor`;
  - `_meta {elapsed_ms, index_freshness, next_cursor}`;
  - `cass pack` produces a token-budgeted, cited, redacted evidence bundle;
  - `cass capabilities --json`;
  - forgiving flag parsing, because agents misspell flags.
- **Redaction.** At ingestion, before SQLite and FTS, using prefix patterns plus a JSON-key walker (`*token`, `authorization`, `cookie`, …). On by default ([redact_secrets.rs](https://github.com/Dicklesworthstone/coding_agent_session_search/blob/main/src/indexer/redact_secrets.rs)).

### 4.4 ctx: Tantivy-only index and session-to-commit "blame"

- **Index.** ctx dropped SQLite for a pure Tantivy index. The complete normalised record is stored in a field, so `show` never reparses the source. The README reports cold indexing at 9.65 s against 155 s for its earlier SQLite pipeline ([README](https://github.com/ctxrs/ctx/blob/main/README.md)).
- **Documents.** One document per *event*, with lineage (`parent_session_id`, `root_session_id`) and exact-match "fact" fields: `fact_file`, `fact_command`, `fact_commit`, `fact_branch`, `fact_pull_request`, … ([schema.rs](https://github.com/ctxrs/ctx/blob/main/crates/ctx-history-index-format/src/schema.rs)).
- **Refresh.** A daemon builds an immutable new "generation", verifies it and publishes it atomically. It keeps one previous generation and hard-links unchanged segments, so a failed refresh leaves the old index live ([storage.md](https://github.com/ctxrs/ctx/blob/main/docs/storage.md)).
- **Blame.** ctx parses recorded shell tool calls with a bounded tokenizer (tracking `cd`) to find `git commit` and PR operations, ties them to the commit IDs printed in tool output, and certifies them against local git. It separates "proven", "possible", "conflicting" and "missing"; merely mentioning a SHA is not proof ([blame.md](https://github.com/ctxrs/ctx/blob/main/docs/blame.md)).
- **Privacy.** No redaction; the import policy drops binaries, images and raw diffs.

### 4.5 agent-sessions and CodMate: native macOS browsers

- **agent-sessions** keeps SQLite with:
  - `files(path, mtime, size)` for incremental skip;
  - `session_meta(…, title, cwd, repo, model, is_housekeeping, parent_session_id)`;
  - one flattened **search blob per session** in external-content FTS5;
  - a separate FTS table for tool input/output.

  Indexing is throttled (one worker, 250–650 ms yields) to protect battery ([DB.swift](https://github.com/jazzyalex/agent-sessions/blob/main/AgentSessions/Indexing/DB.swift), [Energy-and-Performance.md](https://github.com/jazzyalex/agent-sessions/blob/main/docs/Energy-and-Performance.md)). Its distinctive practice is [`tools/agent-watch`](https://github.com/jazzyalex/agent-sessions/blob/main/tools/agent-watch/README.md): a weekly job that diffs upstream CLI versions, fingerprints session schemas against fixtures and checks discovery-path contracts. Format drift is caught on a schedule rather than from user bug reports. Resume builds per-agent commands, e.g. `codex resume <id> || codex -c experimental_resume=<path>`.
- **CodMate** indexes metadata only, in SQLite (`sessions(file_path, file_mtime, file_size, schema_version, parse_error, …)` plus turn previews). Its fast path parses the first ~64 lines and a tail sample. Full-text search shells out to ripgrep with a chunked in-process fallback, caching aggregates per file keyed on mtime ([SessionIndexSQLiteStore.swift](https://github.com/loocor/codmate/blob/main/services/SessionIndexSQLiteStore.swift), [GlobalSearchService.swift](https://github.com/loocor/codmate/blob/main/services/GlobalSearchService.swift)).

### 4.6 claudecodeui (CloudCLI): app database plus polling watchers

- **Index.** Provider files are indexed into `sessions(session_id, provider, provider_session_id, custom_name, project_path, jsonl_path, isArchived, …)`. The app-facing ID is stable; the provider's own ID is filled in once the CLI announces it ([schema.ts](https://github.com/siteboon/claudecodeui/blob/main/server/modules/database/schema.ts)).
- **Titles.**
  - Claude: `~/.claude/history.jsonl`, then `custom-title`/`ai-title`/`last-prompt` read in reverse.
  - Codex: `session_index.jsonl`.
  - Cursor CLI: the workspace comes from a sibling `worker.log`.
- **Consistency.** `scan_state.last_scanned_at` advances only when every provider synchronises successfully. A fork's row is written before the watcher sees its file, so the fork is not indexed twice.
- **Watchers.** chokidar polling every 6 s, ignoring `**/subagents/**` and `**/tool-results/**`, debounced 500 ms, results pushed over WebSocket ([sessions-watcher.service.ts](https://github.com/siteboon/claudecodeui/blob/main/server/modules/providers/services/sessions-watcher.service.ts)).
- **Paging.** Message history is paged **from the tail** (`startIndex = total − offset − limit`), because the newest turns are what a reader opens to ([claude-sessions.provider.ts](https://github.com/siteboon/claudecodeui/blob/main/server/modules/providers/list/claude/claude-sessions.provider.ts)).

### 4.7 cc-sessions-viewer and deja-vu

- **cc-sessions-viewer** (Chinese ecosystem, 7 agents) defines a `SessionSource` trait: `list_sessions, read_session, resume_command, contains_text, watch_target, source_mtime`. There is **no persistent index**. Global search first byte-scans case-insensitively, then parses only user-message text, cached in an mtime-keyed LRU capped at 64 MB after a 1.9 GB Codex corpus pinned memory ([agents/mod.rs](https://github.com/jerrywu001/cc-sessions-viewer/blob/main/src-tauri/src/agents/mod.rs)). Resume runs in an embedded PTY or an external terminal.
- **deja-vu** turns 34 agents' history into typed records: speech, tool-output, files, command with exit status, edit (the exact replaced bytes), and summary (compaction digests). These go into a custom postings index with BM25 × user-turn boost × `1/(1+age_days)`. Appends are taken only when the already-read prefix hash still matches. Redaction happens at index time and yields `[redacted:<kind>]`. `deja secrets --scrub` can optionally rewrite source transcripts, and `deja forget` writes tombstones ([ARCHITECTURE.md](https://github.com/vshulcz/deja-vu/blob/main/docs/ARCHITECTURE.md)).

---

## 5. Tools that own their own log instead of reading the agent's

- **opcode (Claudia).**
  - Lists `~/.claude/projects`, taking each project's path from the first `cwd` in its files. It finds the first user message by a full linear scan and loads a whole session with no paging ([claude.rs](https://github.com/winfunc/opcode/blob/main/src-tauri/src/commands/claude.rs)).
  - Resume runs `claude --resume <id> -p … --output-format stream-json`.
  - Its checkpoint timeline writes **inside** `~/.claude/projects/<p>/.timelines/<session>/`: a `timeline.json` tree (forks are branches), zstd-compressed `messages.jsonl` per checkpoint, and a content-addressed file pool ([checkpoint/](https://github.com/winfunc/opcode/tree/main/src-tauri/src/checkpoint)).
- **Crystal / Nimbalyst.**
  - Never reads `~/.claude/projects`. It stores the stream-json of the process it spawned in its own SQLite (`session_outputs`, `conversation_messages`), declared "the single source of truth". The same document lists duplicate-message and race-condition hazards ([SESSION_OUTPUT_SYSTEM.md](https://github.com/stravu/crystal/blob/main/docs/SESSION_OUTPUT_SYSTEM.md)).
  - Resume uses the captured agent session ID, and deliberately refuses to fall back to `--continue` when the ID is missing ([claudeCodeManager.ts](https://github.com/stravu/crystal/blob/main/main/src/services/panels/claude/claudeCodeManager.ts)).
- **Happy.**
  - In local mode it tails `<session>.jsonl` with a watcher and forwards only entries whose `uuid` (or a summary's `leafUuid`) is new. It keeps watching the *old* file after a resume, because Claude may continue writing there ([sessionScanner.ts](https://github.com/slopus/happy/blob/main/packages/happy-cli/src/claude/utils/sessionScanner.ts)).
  - Its server keeps an ordered, idempotent (`sessionId, localId` unique), end-to-end encrypted message log: AES-256-GCM with a per-session key wrapped by NaCl box ([encryption.md](https://github.com/slopus/happy/blob/main/docs/encryption.md), [schema.prisma](https://github.com/slopus/happy/blob/main/packages/happy-server/prisma/schema.prisma)).
  - Resume from the phone is an RPC to the owning machine's daemon (`requiresSameMachine: true`), because only that machine has the native transcript ([resumeCommand.ts](https://github.com/slopus/happy/blob/main/packages/happy-app/sources/utils/resumeCommand.ts)).

---

## 6. Capture into the repository: SpecStory and entire

**SpecStory** ([specstory-cli](https://github.com/specstoryai/getspecstory/tree/dev/specstory-cli)).
- **Capture.** About 15 providers parse native stores into a neutral `SessionData`, rendered as Markdown to `.specstory/history/<YYYY-MM-DD_HH-MM-SS>Z-<slug>.md`: one file per session, rewritten in place, skipped when unchanged ([session.go](https://github.com/specstoryai/getspecstory/blob/dev/specstory-cli/pkg/session/session.go)). `specstory run claude` launches the agent and watches its project directory (fsnotify plus polling); `sync` backfills; IDE providers watch until Ctrl-C.
- **Redaction.** On by default, using the betterleaks ruleset, applied before writing and before cloud upload. Moving to an RE2 engine with about 100 KB chunks cut a 10 MB JSONL from 1m48s to 815 ms ([SECRET-REDACTION-PERFORMANCE.md](https://github.com/specstoryai/getspecstory/blob/dev/specstory-cli/docs/SECRET-REDACTION-PERFORMANCE.md)).
- **Global index.** `~/.specstory/sessions.db`, stated to be "a derived cache that can always be rebuilt from the native stores" ([SESSIONS-DB.md](https://github.com/specstoryai/getspecstory/blob/dev/specstory-cli/docs/SESSIONS-DB.md)).
  - Key `(agent, session_id)`; freshness `(size, mtime, index_version)`; a soft-delete tombstone that never touches the native file.
  - FTS5 `sessions_fts(session_id UNINDEXED, agent UNINDEXED, name, body)`, reached via `fts_rowid` because lookups on UNINDEXED columns scan the whole table.
  - It is filled as a side effect of `run`/`sync`/`watch`, with a cold `reindex` to close the "witness gap" for sessions SpecStory never saw.
- **Cross-agent resume.** `specstory resume` can resume a session **into a different agent** by reconstructing a native file (Claude↔Codex first) with a `specstorySourceSessionId` breadcrumb. The fidelity target is "loads and conveys the gist"; tool calls are not replayed ([SESSION-PORTABILITY.md](https://github.com/specstoryai/getspecstory/blob/dev/specstory-cli/docs/SESSION-PORTABILITY.md)).

**entire** ([sessions-and-checkpoints.md](https://github.com/entireio/cli/blob/main/docs/architecture/sessions-and-checkpoints.md)).
- **Capture.** Hooks installed per repo map each agent's native events to `SessionStart/TurnStart/TurnEnd/Compaction/SubagentStart/…` ([event.go](https://github.com/entireio/cli/blob/main/cmd/entire/cli/agent/event.go)). Work accumulates on a shadow branch.
- **On commit.** A `prepare-commit-msg` hook adds an `Entire-Checkpoint: <id>` trailer. `post-commit` condenses the session into `refs/entire/checkpoints/<shard>/<id>`, holding `full.jsonl` (sanitised and redacted), a compact `transcript.jsonl`, `prompt.txt` and a content hash. These refs push and fetch like any git ref.
- **Redaction order.** Sanitise → externalise images (base64 otherwise trips entropy rules) → redact. Redaction uses betterleaks, Shannon entropy ≥ 4.5, DSN/URI regexes, JSON-key rules, optional PII and an optional external privacy filter ([redact/](https://github.com/entireio/cli/tree/main/redact)).
- **Search.** Goes to entire.io's cloud semantic search; there is no local full-text index ([search.go](https://github.com/entireio/cli/blob/main/cmd/entire/cli/search/search.go)).

---

## 7. Interchange and observability formats

- **Letta.**
  - **Context repositories** (announced 2026-02-12) are git-backed Markdown memory for Letta Code. Conversation history is *input* to memory, not part of the repo ([blog](https://www.letta.com/blog/context-repositories/)).
  - **`letta trajectories export`** writes one JSON per session plus a `manifest.json` (`source`, native `id`, a stable 10-hex `sessionId` = sha256 of the source-scoped native id, `project`, `model`, `startedAt`/`endedAt`, counts, `firstUserPrompt`) for a history-analyser subagent to read ([letta-code](https://github.com/letta-ai/letta-code)).
  - **[`@letta-ai/trajectory`](https://github.com/letta-ai/trajectory)** (created 2026-07) is a stateless normaliser: `normalizeTranscript({source, transcript}) → {records, diagnostics}`, covering claude-code, codex, cursor, gemini-cli, opencode, openhands, ATIF and more.
    - Records form a flat, chat-like array: one `meta` record, then `user`/`assistant`, `assistant` with `tool_calls`, `tool` with `tool_call_id` and optional `ok`, `reasoning`, and `observation`.
    - `ok` is set only when the source has an authoritative flag; result text is never read as success or failure.
    - Each adapter documents what it drops.
  - **The older [`.af` Agent File](https://github.com/letta-ai/agent-file)** separates full `messages[]` from `in_context_message_ids[]`: the whole history versus what is currently in the window. That is a useful model for compaction, but `.af` is tied to the retired Letta server ([agent_file.py, archive branch](https://github.com/letta-ai/letta/blob/archive/letta/schemas/agent_file.py)).
- **ATIF (Agent Trajectory Interchange Format).** Harbor's [RFC 0001](https://github.com/harbor-framework/harbor/blob/main/rfcs/0001-trajectory-format.md), v1.8 (April 2026).
  - Root: `session_id`, `trajectory_id`, `agent {name, version, model_name, tool_definitions}`, `steps[]`, `final_metrics`, `continued_trajectory_ref`, `subagent_trajectories[]`.
  - Each step: `source` (system/user/agent), `message`, `reasoning_content`, `tool_calls[]`, `observation.results[]`, `metrics`, `is_copied_context`.
  - A `boundary` of `replace|append|truncate` marks compaction.
  - Harbor ships converters from claude-code, codex, cursor-cli, gemini-cli and opencode. NVIDIA NeMo Agent Toolkit has an [`nat.atif` module](https://docs.nvidia.com/nemo/agent-toolkit/1.8/api/nat/atif/index.html).
- **OpenTelemetry GenAI semantic conventions.** Now in their own repo, [semantic-conventions-genai](https://github.com/open-telemetry/semantic-conventions-genai), status **Development**.
  - `gen_ai.input.messages` / `gen_ai.output.messages` are `{role, parts[{type: text|tool_call|tool_call_response}]}`, are **opt-in**, and carry a PII warning. `gen_ai.conversation.id` correlates one conversation.
  - Claude Code's export ([monitoring docs](https://code.claude.com/docs/en/monitoring-usage)) has content off by default: `OTEL_LOG_USER_PROMPTS`, `OTEL_LOG_TOOL_DETAILS` and related switches turn it on, content is truncated at 60 KB, and events carry `session.id` and a `message.uuid` that matches the transcript line.
  - Codex has an `[otel]` table with `log_user_prompt = false` by default ([config reference](https://learn.chatgpt.com/docs/config-file/config-reference)).
  - Neither export reconstructs a transcript. Langfuse's own guide traces Claude Code and Codex with Stop hooks that re-read the transcript file ([Langfuse](https://langfuse.com/resources/engineering/coding-agent-tracing)).
- **Agent Trace.** An RFC (v0.1.0, January 2026) from Cursor, [agent-trace.dev](https://agent-trace.dev/). It records *pointers*, not transcripts: `files[].conversations[{url, contributor{type, model_id}, ranges[{start_line, end_line, content_hash}]}]`, with storage deliberately unspecified. A transcript browser is a natural target for `conversations[].url`.
- **dsh-chat-import.** Normalises 25+ agents into "Interchange v1" (`turns[{prompt, steps[{content, toolCalls, toolResults}]}]`) and can export back to Claude, Codex or Kimi formats. It enforces "every tool call has a result" (filling empty ones), and publishes a per-source capability matrix of what each format loses: Cursor has no tool results; Codex reasoning is summary-only ([INTERCHANGE.md](https://github.com/Nwflower/dsh-chat-import/blob/main/docs/INTERCHANGE.md)).

---

## Comparison

| Product | Reads native files? | Persistent index | Freshness key | Full-text search | Subagents | Compaction | Redaction | Resume / fork |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Claude Code picker / Agent SDK | own | none (head/tail 64 KiB per list) | mtime | title/prompt filter | separate API | summary included, `logicalParentUuid` not followed | none | resume, `/branch`, `--fork-session` |
| Codex CLI | own | derived SQLite (`threads`, projections) | backfill + byte-offset cursor | ripgrep | spawn edges | `compacted` item | none | resume, fork, archive, delete |
| ccusage | yes | none | none (full re-read, parallel) | n/a | walked, deduped | n/a | none | n/a |
| claude-code-log | yes | SQLite (in `~/.claude`) | mtime ±1 s + size + subagent dir | FTS5 contentless | spliced under Task call | text prefix + boundary | none | `claude -r` |
| history-viewer | yes | JSON per project (in `~/.claude`) | mtime + size + byte offset | Aho-Corasick + LRU | listed | follows logical parent | none | allowlisted command |
| claude-code-viewer | yes | SQLite (own dir) | mtime | FTS5 trigram | matched by `sessionId` | flag in schema | none | Agent SDK |
| cc-switch | yes | none | none | FlexSearch, metadata only | skipped | n/a | none | terminal command; hard delete |
| agentsview | yes | SQLite archive | stat + inode + tail anchor + prefix hash | FTS5 (+CJK) | own rows | boundary column | detect + snippet redaction | n/a |
| cass | yes | SQLite + Tantivy-family | mtime + UNIQUE(conv, idx) | BM25 + recency (+ vectors) | normalised | n/a | at ingest | n/a |
| ctx | yes | Tantivy generations | rebuild generation | BM25 + fact filters | lineage fields | n/a | none | n/a |
| agent-sessions | yes | SQLite | mtime + size | FTS5 per-session blob | parent id | n/a | none | per-agent command |
| SpecStory | yes | SQLite + Markdown copies | size + mtime + index_version | FTS5 | per provider | per provider | on by default | cross-agent rebuild |
| entire | hooks | git refs | hook events | cloud | subagent events | Compaction event | multi-layer | via checkpoint |
| Crystal | no (own stream log) | SQLite | n/a | n/a | n/a | n/a | none | stored agent session ID |
| Happy | tails JSONL | encrypted server log | uuid set | n/a | n/a | summary `leafUuid` | E2E encryption | same-machine RPC |

---

## Patterns and trade-offs

**Parsing: the field converges on tolerant readers.** Every mature reader skips or flags bad lines rather than failing the file, because the vendors say outright the format changes between releases. Readers split three ways on unknown record types:
- **Drop silently** (the Agent SDK, ccusage).
- **Keep as passthrough so the tree stays intact** (claude-code-log).
- **Keep and flag the line** (claude-code-viewer's `x-error`).

Only the passthrough approach survives a new record type that sits *inside* the `parentUuid` chain. The strongest drift defences are operational, not code:
- agentsview bumps a `dataVersion` and keeps a `parse-diff` tool;
- agent-sessions runs weekly schema fingerprinting against fixtures;
- dsh-chat-import and trajectory publish per-source "what this loses" lists.

**Parsing: order is a tree, not the file.** Claude Code transcripts must be read by walking `parentUuid` from the right leaf. The vendor's own reader and claude-code-log do this; readers that print in file order show abandoned branches. Readers split on compaction: follow `logicalParentUuid` to show the whole pre-compaction history (history-viewer), or show the summary in its place (the Agent SDK, "matching VS Code"). Codex's own format has migrated from event-only to paginated items. Any Codex reader needs both paths, plus `.jsonl.zst`.

**Parsing: whose words are these.** Every tool re-derives a "first real prompt" by skipping harness markup. The skip lists differ and keep growing: the SDK's regex; cc-switch's caveat and command checks; claude-history dropping `/clear`-only sessions; claude-code-viewer's slash-command list. Only claude-code-log keeps the markup as typed, folded message kinds instead of dropping it. Titles converge on one priority order: user-set (`custom-title`, Codex `session_index` or `threads.title`), then the agent's generated title (`ai-title`), then the first real prompt, then the project basename.

**Listing speed: two schools.**
- **No index.** Stat everything and read a bounded head and tail per file: the SDK uses 64 KiB each way, cc-switch 10 lines plus a 16 KB tail, Codex 10 records under a 10,000-file scan cap. This is correct by construction and needs no invalidation, but costs O(files) per request.
- **Derived index.** Keyed on (mtime, size), with the best versions adding inode, byte offset and a prefix or tail hash to make append-only reads O(delta) and to detect rewrites (agentsview, deja-vu, history-viewer's offsets).

Everyone who indexes treats the index as rebuildable: SpecStory says so in writing; cass and ctx publish atomically and rebuild on a schema-hash mismatch; claude-code-viewer drops its DB when a migration fails. The split is on *where* the index lives:
- **Inside the agent's directory:** claude-code-log's SQLite, history-viewer's JSON, opcode's `.timelines`.
- **In the tool's own home:** everyone else.

**Search: three tiers.** Metadata-only search on the client (cc-switch) is cheap but can't find what was said. Grep-on-demand (Codex's ripgrep, CodMate, cc-sessions-viewer, history-viewer's Aho-Corasick) needs no index but scales with corpus size. A full-text index is the third tier:
- FTS5 with porter, unicode61, trigram (for substrings and CJK), or a contentless variant to save space;
- Tantivy for speed (ctx reports 16× faster cold indexing than its SQLite pipeline);
- BM25 blended with recency, since recent sessions are what people look for.

**Privacy: split between detect, redact and nothing.** No agent redacts its own transcripts, and most single-agent viewers do nothing. The redacting tools differ on *where* and *what*:
- **Where:** at ingest before anything is indexed (cass, deja-vu), at output and upload (SpecStory, entire), or detect-and-record with snippet masking while keeping raw content (agentsview).
- **What:** prefix and anchored vendor rules have low false positives and run inline. Entropy and heuristic rules are noisier and are often run later or behind an option. Base64 images have to be removed first, or they trip entropy rules (entire).

Only deja-vu offers to rewrite the source files, and only on explicit request. Observability exports reach the same answer from the other side: content capture is off by default in OTel GenAI, Claude Code and Codex alike.

**Resume and fork: the agent does it, the tool builds the command.** Every browser resumes by launching the agent's own command in the right directory (`cd <cwd> && claude --resume <id>`, `codex resume <id>`, opencode `-s <id>`). The implementations vary in how they launch it:
- **Clipboard:** Claude Code's own picker for other projects, cc-switch off macOS.
- **External terminal:** osascript or each terminal's own CLI.
- **Embedded PTY.**
- **The SDK:** claude-code-viewer, Crystal and opcode's headless `-p`.

Forking is a first-class agent feature in both (`/branch`/`--fork-session`, `codex fork` with `forked_from_id`), so tools expose it by passing the flag (raine's `Ctrl+F`) rather than copying files. Only SpecStory attempts cross-agent resume, and it states its fidelity target as "the gist". Owning a separate log (Crystal, Happy) buys ordering control and encryption, at the cost of a second source of truth that can disagree with the agent's.

**Cross-agent schema: convergence on a small core.** Across agentsview, cass, ctx, cc-switch, trajectory, ATIF and dsh the shared fields are:
- agent/provider;
- the native session ID (kept, because resume needs it) plus sometimes a stable derived ID;
- cwd/project;
- parent/root session for subagents and forks;
- source path, start/end time;
- role, content, timestamp per message;
- tool calls as their own rows or records with call ID, name, args and result;
- model and token usage.

Richer schemas add a fidelity marker (agentsview's `transcript_fidelity`, ATIF's `is_copied_context`, the `.af` in-context-ID list) so a reader can tell "full" from "summary". ATIF is the most complete and the most adopted interchange target; the OTel GenAI parts schema is the standards-track wire shape but still unstable. Nobody treats OTel exports as a transcript source.

---

## Worth borrowing / worth avoiding

**Worth borrowing**
- **Head/tail reads for listing.** Read a bounded head for `cwd`, start time and first prompt, and a bounded tail for last activity and the latest title record, instead of parsing whole files. That's how the vendor's own SDK lists sessions, and it holds up against 300 MB files.
- **A freshness key of (mtime, size), plus a prefix or tail anchor if appends are read incrementally.** agentsview's rule is the safe version: resume at a newline-aligned offset only if identity matches, the file only grew and the anchor still matches; otherwise reparse.
- **Walk `parentUuid` from the latest main-chain leaf.** Exclude `isMeta` and sidechain lines, keep compact summaries, and make following `logicalParentUuid` a deliberate choice.
- **Treat Codex as two formats and two encodings.** Legacy vs paginated history, `.jsonl` vs `.jsonl.zst`, and titles from `session_index.jsonl` (last entry wins) or the `threads` table.
- **Keep harness markup, folded.** claude-code-log's typed message kinds read better than a growing skip regex, and don't claim a turn said less than it did.
- **Identify harness blocks by shape, not by name.** Every name-based skip list in the survey is out of date.
- **A derived, disposable index, published atomically.** Fingerprint the schema or parser version, and rebuild rather than migrate (cass, ctx, SpecStory, claude-code-viewer).
- **Redact at the boundary where content leaves the reader.** Anchored vendor-prefix rules inline, heuristics optional, images stripped before entropy checks, and findings counted so a UI can say "this session contains N secrets".
- **Resume through the agent's own command.** Resolve the working directory from the transcript, quote it, and resolve by ID. Claude Code's "exactly one match or not-found" rule for duplicate IDs is a good guard.
- **Tail-first paging for opening a long session, plus the total turn count.** The newest turns are what readers want; claudecodeui returns `{messages, total, hasMore}`.
- **Scheduled format-drift checks against fixtures** (agent-sessions' agent-watch), and a per-source "what this format loses" list (dsh-chat-import, trajectory).
- **Map to an existing interchange shape if a cross-agent schema is needed.** Trajectory's flat records for reading, ATIF for export, rather than inventing one.

**Worth avoiding**
- **Decoding the project directory name back into a path.** The encoding is lossy; take `cwd` from the file.
- **Globbing `*.jsonl` naively.** It picks up `.orphaned-…jsonl` duplicates and flat `agent-*` subagent files, and misses Codex's `.jsonl.zst` rollouts older than a week.
- **Printing Claude Code transcripts in file order.** It surfaces rewound branches as if they were the conversation.
- **Writing caches, timelines or rewritten headers inside the agent's own directories** (claude-code-log's DB, history-viewer's JSON, opcode's `.timelines`, cc-switch's Codex provider rewrite). They are swept, purged or misread by the agent, and blur what is the agent's own state.
- **Treating a second, tool-owned log as history** when the agent already keeps one. Crystal's own docs list the duplicate and race hazards that follow.
- **Assuming "all history" is available.** Claude Code deletes transcripts after 30 days by default, so a browser shows a window unless it archives. Archiving means holding every secret the agent saw.
- **Relying on OTel exports to rebuild conversations.** Content capture is off by default and truncated when on.
- **Blocking the agent's writer.** Open the other process's SQLite read-only, in WAL mode, with a `busy_timeout`, and watch the `-wal` file (cc-switch on Codex's DB, SpecStory and agent-sessions on Cursor).
- **Unbounded in-memory text caches over the whole corpus.** cc-sessions-viewer had to cap its cache at 64 MB after a 1.9 GB Codex corpus.
