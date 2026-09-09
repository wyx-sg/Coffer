# Knowledge

**Knowledge** is Coffer's one store of everything your agents should know: the entries an agent (or you) wrote down, and the documents you ingested. Both live as Markdown files under `~/.coffer/knowledge/`, both are indexed by the same SQLite index, and both come back from the same search. Files are the source of truth; the index is rebuildable at any time with `coffer knowledge reindex`.

Coffer used to expose this as two resource kinds — a *knowledge base* you could only read, and a *memory* only agents wrote to. They were never two things. `documents`, `chunks`, FTS5 and sqlite-vec were shared from the very beginning; only the facade was doubled. In practice the knowledge base sat empty, memory already had a `knowledge/` lane of its own, and the split forced every caller to answer "is this memory or knowledge?" before it could pick a tool — a question with no meaning on the calling side. There is now one kind, `knowledge`, one storage root, and one search across the whole of it.

## Scopes

A knowledge scope is a resource named `knowledge:<scope>`. The name decides how the scope behaves:

- **`global`** — everything true everywhere, regardless of which repo you are in. Auto-provisions the first time anything is written to it.
- **`project-<ULID>`** — one project, resolved from the git root of the agent's working directory. Also auto-provisions on first use, so you never create one by hand.
- **any other name** — a collection you created deliberately, e.g. `handbook`. These do **not** auto-provision: silently creating a scope because someone typo'd a name would be worse than an error.

```bash
coffer knowledge create handbook --description "Company onboarding docs"
coffer knowledge list
coffer knowledge describe global
```

Retrieval spans both lanes of a scope, and an agent that names no scope gets the scope of its current project, falling back to `global`.

## What a scope holds

`~/.coffer/knowledge/<scope>/` is a plain directory tree you can read, edit, grep, and back up with ordinary tools:

| Path           | What lives there                                                                  |
| -------------- | --------------------------------------------------------------------------------- |
| `knowledge/`   | Entries an agent wrote. Fresh ones land in `knowledge/inbox/` before consolidation. |
| `inbox/`       | Ingested documents, normalized to Markdown.                                        |
| `rules/`       | Behavioural rules, injected into an agent at session start.                        |
| `handoff/`     | Working state, one file per git branch.                                            |
| `superseded/`  | Retired topic docs, kept rather than deleted.                                      |
| `.raw/`        | The untouched originals of ingested files. Hidden, so ripgrep skips it.            |

Hand-editing any of these files is fine and expected — Coffer rescans the tree before searching, so out-of-band edits are picked up.

## Writing entries

An entry is a fact, a decision, or a preference worth surviving the session. It is stored verbatim: there is no LLM at write time.

```bash
coffer knowledge remember global "Prefer pnpm over npm in all repos" --title pkg-manager
coffer knowledge entries global                       # list them
coffer knowledge get global <entry-id>
coffer knowledge edit-entry global <entry-id> "…"     # curate
coffer knowledge forget global <entry-id>
```

An entry's size is capped by the scope's `max_entry_chars`; raise it with `coffer knowledge configure <scope> --max-entry-chars N`.

## Ingesting documents

Hand Coffer a file in any format and it converts it to Markdown, keeps the original in `.raw/`, chunks it, and indexes it.

```bash
coffer knowledge ingest handbook ./onboarding.pdf     # any format → Markdown
coffer knowledge ingest handbook ./notes.docx
coffer knowledge documents handbook                   # what's inside
coffer knowledge read handbook <document-id>
```

- Conversion covers pdf, docx, pptx, xlsx, html and more (25 MB default cap, `--max-document-mb` at create time). Re-ingesting the same source needs `--replace`.
- A document you hand-edit is yours: `coffer knowledge edit` writes it, and it is not silently re-converted from its raw original. `coffer knowledge reconvert` re-runs conversion when you do want that.
- Coffer remembers where an ingested file came from. `coffer knowledge check-sources <scope>` reports which originals have changed on disk and `coffer knowledge update-source <scope> <document-id>` pulls the new version in. Turn this into a background refresh with `coffer knowledge configure <scope> --auto-update-sources`.

## Retrieval

One search covers entries and documents together — that unification is the whole point.

```bash
coffer knowledge search handbook "how do I reset my password"   # ranked passages
coffer knowledge recall global "which package manager?"         # ranked entries + docs
coffer knowledge grep handbook "TODO"                           # exact / regex, no index
```

Under the hood the engine has four modes — `grep` (literal/regex over the Markdown), `keyword` (FTS5 with BM25), `vector` (sqlite-vec nearest-neighbour), and `hybrid` (reciprocal-rank fusion over keyword + vector). **Callers never pick a mode.** The scope's configuration decides, and the engine chooses per query; a mode argument would only ask the caller to guess at an internal detail.

Vector retrieval is opt-in per scope:

```bash
coffer knowledge create research --enable-vector
coffer knowledge configure handbook --enable-vector
```

Embedding itself is configured **once for the installation**, under **Settings → Embedding** in the web UI. A scope carries no embedding fields of its own; it opts in purely by listing `vector` among its retrieval modes. A scope that asks for vector with no embedding configured falls back to keyword rather than erroring.

The index is a projection, never the truth. `coffer knowledge reindex <scope>` rebuilds it from the Markdown on disk.

## Rules and handoff

Two lanes are less about search and more about how an agent starts and stops work.

**Rules** are the behavioural instructions a scope carries — how you want work done in this project. They are injected into the agent at session start, so an agent follows them without having to search first.

```bash
coffer knowledge rules global
```

**Handoff** is the working state of a paused task — current task, next steps, files in flight, open questions — saved per project and git branch. An agent writes it with `coffer__set_handoff` when pausing and reads it back with `coffer__resume` when picking the branch up again, so the next session starts where the last one stopped.

```bash
coffer knowledge handoff project-<ULID>
```

## Curation

Entries accumulate. Coffer consolidates the `knowledge/inbox/` lane into topic docs, retiring what it replaces into `superseded/` and appending what it did to a changelog.

```bash
coffer knowledge organize <scope>            # fold the inbox into topic docs
coffer knowledge reorg <scope>               # re-shape the topic docs themselves
coffer knowledge consolidation-log <scope>   # what was consolidated, and when
coffer knowledge merge-scan <scope>          # find near-duplicate entries
coffer knowledge merge <scope>               # merge them
coffer knowledge clear <scope>               # drop every entry in a scope
```

## The CLI

Everything above lives under one group, `coffer knowledge`:

| Area      | Commands                                                                                   |
| --------- | ------------------------------------------------------------------------------------------ |
| Scopes    | `list` · `describe` · `create` · `configure` · `label` · `delete`                          |
| Entries   | `remember` · `entries` · `get` · `edit-entry` · `forget` · `clear` · `recall`               |
| Documents | `ingest` · `documents` · `read` · `edit` · `reconvert` · `delete-doc` · `reindex`           |
| Retrieval | `search` · `grep`                                                                           |
| Lanes     | `organize` · `reorg` · `rules` · `handoff` · `consolidation-log`                            |
| Sources   | `check-sources` · `update-source`                                                           |
| Merging   | `merge-scan` · `merge`                                                                      |

## The REST surface

The daemon serves knowledge under `/api/v1/knowledge`, with the scope as a path segment and `entries` / `documents` as sub-resources:

| Route                                            | Purpose                            |
| ------------------------------------------------ | ---------------------------------- |
| `GET`/`POST` `/api/v1/knowledge`                 | List scopes; create a collection.  |
| `GET`/`PATCH` `/api/v1/knowledge/{scope}`        | Read or reconfigure one scope.     |
| `/api/v1/knowledge/{scope}/entries`              | Entry CRUD.                        |
| `/api/v1/knowledge/{scope}/documents`            | Ingest, list, read, edit, delete.  |
| `/api/v1/knowledge/{scope}/search` · `/recall` · `/grep` | Retrieval.                 |
| `/api/v1/knowledge/{scope}/rules` · `/handoff` · `/consolidation-log` | Lane views. |
| `/api/v1/knowledge/{scope}/reindex` · `/organize` · `/reorg` · `/check-sources` | Maintenance. |

Deleting a whole scope goes through the kind-agnostic resource route, `DELETE /api/v1/resources/knowledge/{name}` — there is no `DELETE /api/v1/knowledge/{scope}`.

## The MCP tools

Every connected MCP client gets eight built-in tools. Each takes an optional `scope`, defaulting to the current project's scope and falling back to `global`:

| Tool                 | What it does                                                                       |
| -------------------- | ---------------------------------------------------------------------------------- |
| `coffer__search`     | Ranked snippets across entries **and** documents. The engine picks the mode.       |
| `coffer__grep`       | Literal or regex match over every Markdown file in a scope, with file and line.     |
| `coffer__read`       | One item in full by id — entry or document, resolved automatically.                 |
| `coffer__list`       | What a scope holds, or `all=true` for every scope with its counts.                  |
| `coffer__write`      | File an entry, store a Markdown document (`filename`), or rewrite one in full (`id`). |
| `coffer__delete`     | Remove one entry or document by id, file included.                                  |
| `coffer__set_handoff`| Save the working state for the current project + branch.                           |
| `coffer__resume`     | Read that handoff back.                                                            |

Agents both read and write here — an entry one agent records is what the next agent recalls, which is the point of keeping it in Coffer rather than in any single agent's own store.

## In the web UI

Knowledge is one page under **Resources**. `/knowledge` lists your scopes with entry counts, document counts, disk usage, and which retrieval modes are indexed; `/knowledge/:scope` opens one scope with five tabs — **Entries**, **Documents**, **Rules**, **Handoff**, and **Changelog**. Create a collection, drag files in, browse and curate entries, and search, all from there.

[Channels →](/guide/channels)
