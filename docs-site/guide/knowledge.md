# Knowledge

**Knowledge** is Coffer's one store of everything your agents should know: the notes an agent (or you) wrote down, and the documents you ingested. Both live as Markdown files under `~/.coffer/knowledge/`, both are indexed by the same SQLite index, and both come back from the same search. Files are the source of truth; the index is rebuildable at any time with `coffer knowledge reindex`.

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

| Path        | What lives there                                                        |
| ----------- | ----------------------------------------------------------------------- |
| `notes/`    | What an agent or you wrote. `coffer__write` lands here.                  |
| `docs/`     | Ingested documents, normalized to Markdown.                             |
| `.raw/`     | The untouched originals of ingested files. Hidden, so ripgrep skips it. |
| `.history/` | Note revisions the tidy pass replaced. Hidden, for the same reason.     |

Two content lanes, and two hidden archives behind them. There is nothing else: a note is a note whether an agent just wrote it or the tidy pass has folded it into a topic document since.

Hand-editing any of these files is fine and expected — Coffer rescans the tree before searching, so out-of-band edits are picked up.

## Writing notes

A note is a fact, a decision, or a preference worth surviving the session. It lands in `notes/` and is stored verbatim: there is no LLM at write time.

```bash
coffer knowledge remember global "Prefer pnpm over npm in all repos" --title pkg-manager
coffer knowledge entries global                       # list them
coffer knowledge get global <entry-id>
coffer knowledge edit-entry global <entry-id> "…"     # curate
coffer knowledge forget global <entry-id>
```

A note's size is capped by the scope's `max_entry_chars`; raise it with `coffer knowledge configure <scope> --max-entry-chars N`.

## Ingesting documents

Hand Coffer a file in any format and it converts it to Markdown, files the result under `docs/`, keeps the original in `.raw/`, chunks it, and indexes it.

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

One search covers notes and documents together — that unification is the whole point.

```bash
coffer knowledge search handbook "how do I reset my password"   # ranked passages
coffer knowledge recall global "which package manager?"         # ranked notes + docs
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

## The tidy pass

Notes accumulate, and the same fact gets written twice. A periodic **tidy pass** merges duplicate notes and rewrites them into coherent topic documents, in place, inside `notes/`.

It arms itself two ways, because they cover different gaps. **On idle**: each write re-arms one coalescing timer, and after a quiet spell the scopes that changed are tidied — this is what makes it feel like Coffer tidies up after a session ends. **On an interval**: a periodic sweep over every scope, one catch-up pass when the daemon starts and then every few hours. The sweep catches what the idle timer structurally cannot — files you edited in your own editor, a daemon restarted before its timer fired, and scopes nothing has written to lately.

Both paths take the scope's write lock, so a sweep and a just-fired timer serialize rather than race, and with no internal model configured the pass does nothing at all. A pass that changed something is recorded in Coffer's audit log as `knowledge_tidied`; a pass that left the notes as it found them reports nothing. There is no per-scope changelog file.

The pass rewrites text you and your agents wrote, unattended. Before any overwrite or merge it moves the prior revision into `.history/`, so a rewrite is always recoverable — that archive is the whole safety net, and there is no diff to approve before a pass lands.

Trigger one by hand whenever you want:

```bash
coffer knowledge organize <scope>            # run the tidy pass now
coffer knowledge clear <scope>               # drop every note in a scope
```

The detail page has a **Tidy** button that does the same thing.

## The CLI

Everything above lives under one group, `coffer knowledge`:

| Area      | Commands                                                                                   |
| --------- | ------------------------------------------------------------------------------------------ |
| Scopes    | `list` · `describe` · `create` · `configure` · `label` · `delete`                          |
| Notes     | `remember` · `entries` · `get` · `edit-entry` · `forget` · `clear` · `recall`               |
| Documents | `ingest` · `documents` · `read` · `edit` · `reconvert` · `delete-doc` · `reindex`           |
| Retrieval | `search` · `grep`                                                                           |
| Tidy      | `organize`                                                                                  |
| Sources   | `check-sources` · `update-source`                                                           |

## The REST surface

The daemon serves knowledge under `/api/v1/knowledge`, with the scope as a path segment and `entries` / `documents` as sub-resources:

| Route                                            | Purpose                            |
| ------------------------------------------------ | ---------------------------------- |
| `GET`/`POST` `/api/v1/knowledge`                 | List scopes; create a collection.  |
| `GET`/`PATCH` `/api/v1/knowledge/{scope}`        | Read or reconfigure one scope.     |
| `/api/v1/knowledge/{scope}/entries`              | Note CRUD.                         |
| `/api/v1/knowledge/{scope}/documents`            | Ingest, list, read, edit, delete.  |
| `/api/v1/knowledge/{scope}/search` · `/recall` · `/grep` | Retrieval.                 |
| `/api/v1/knowledge/{scope}/organize`             | Run the tidy pass now.             |
| `/api/v1/knowledge/{scope}/reindex` · `/check-sources` | Maintenance.                 |

Deleting a whole scope goes through the kind-agnostic resource route, `DELETE /api/v1/resources/knowledge/{name}` — there is no `DELETE /api/v1/knowledge/{scope}`.

## The MCP tools

Every connected MCP client gets six built-in knowledge tools. Each takes an optional `scope`, defaulting to the current project's scope and falling back to `global`:

| Tool                 | What it does                                                                       |
| -------------------- | ---------------------------------------------------------------------------------- |
| `coffer__search`     | Ranked snippets across notes **and** documents. The engine picks the mode.         |
| `coffer__grep`       | Literal or regex match over every Markdown file in a scope, with file and line.     |
| `coffer__read`       | One item in full by id — note or document, resolved automatically.                  |
| `coffer__list`       | What a scope holds, or `all=true` for every scope with its counts.                  |
| `coffer__write`      | File a note, store a Markdown document (`filename`), or rewrite one in full (`id`).  |
| `coffer__delete`     | Remove one note or document by id, file included.                                   |

Agents both read and write here — a note one agent records is what the next agent recalls, which is the point of keeping it in Coffer rather than in any single agent's own store.

## In the web UI

Knowledge is one page under **Resources**. `/knowledge` lists your scopes with note counts, document counts and disk usage; `/knowledge/:scope` opens one scope with two tabs — **Documents** and **Notes** — and a filter box above the tree that matches filenames as you type. Create a collection, drag files in, browse and curate notes, and run a tidy pass, all from there. Server-side retrieval stays where it belongs: `coffer__search` for agents, `coffer knowledge recall` for the CLI.

[Channels →](/guide/channels)
