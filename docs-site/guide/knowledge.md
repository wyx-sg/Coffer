# Knowledge

**Knowledge** is Coffer's one store of everything your agents should know — what an agent (or you) wrote down, and the documents you uploaded. It is a directory of Markdown files under `~/.coffer/knowledge/`, one folder per collection, and those files are the whole of it. There is no index: no vector store, no full-text tables, nothing in `coffer.db` to keep in step with the disk. A file you edited in your own editor, a file an agent just wrote, and a file `git` pulled in all look the same to Coffer, because there is nothing in between.

Coffer used to embed these files and rank retrieval by meaning. That capability was removed deliberately: retrieval is now a literal text search over the files themselves. Nothing is built, rebuilt, or kept fresh, and nothing can be stale.

## Collections

A collection is a resource named `knowledge:<name>` and the directory `~/.coffer/knowledge/<name>/`. The two appear together, and only because you said so — nothing creates a collection as a side effect of a read or a write, so a name you typo'd is an error rather than a new, silently empty collection.

```bash
coffer knowledge create handbook --description "Company onboarding docs"
coffer knowledge collections
coffer resource delete knowledge:handbook     # collection lifecycle is a Resource concern
```

Because a collection is a Resource, the framework's per-agent scope decides who may read it. An agent's calls span every collection activated for that agent by default, and there is no collection an agent is authorized for that it has to ask for by name.

There is no **scope** argument on any knowledge tool — scope is Coffer's, decided per agent, and not something a caller can widen. `grep` and `search` do take an optional `collection` argument, but it only ever *narrows*: it restricts the pass to one collection the caller could already see. Omitting it searches every collection the caller may read.

That authorization is a convention, not a security boundary: an agent holding shell tools can read the directory itself. It prevents mistaken retrieval, not deliberate access.

## What a collection holds

`~/.coffer/knowledge/<collection>/` is a plain directory tree you can read, edit, grep and back up with ordinary tools. Below the collection you nest folders however you like; Coffer assigns none of that structure any meaning of its own.

Every file is Markdown with frontmatter carrying a title and a one-sentence description. The description is not decoration — it is what someone browsing the catalogue chooses from, so write it as "what is in here, and when would I want it". A `README.md` describes the folder it sits in rather than counting as one of its files.

Coffer creates exactly two directories for itself, both dot-prefixed so ripgrep skips them and the catalogue walks past them:

| Path        | What lives there                                                          |
| ----------- | ------------------------------------------------------------------------- |
| `.raw/`     | The original bytes behind an uploaded document, so a bad conversion can be redone. |
| `.history/` | The revisions the tidy pass superseded.                                   |

Hand-editing any of this is fine and expected. There is no write path to hook and no reindex step to forget: the next search reads the file as it is on disk.

## Writing files

```bash
coffer knowledge write --in handbook \
  --title "Package manager" \
  --description "Which package manager every repo here uses, and why" \
  --body "Prefer pnpm over npm in all repos."

coffer knowledge ls handbook                       # one level of the catalogue
coffer knowledge read handbook/package-manager.md
coffer knowledge write --path handbook/package-manager.md --title … --description … --body …
coffer knowledge delete handbook/package-manager.md
```

A write is stored verbatim — there is no LLM at write time, and an agent never has to think about filing. `--in` creates a new file in a collection or folder; `--path` replaces an existing one. Dropping a Markdown file into the directory with any editor is an equally complete way to add knowledge.

## Uploading documents

Hand Coffer a file in any format and it converts it to Markdown and files the result as an ordinary knowledge file, keeping the original in `.raw/`.

```bash
coffer knowledge upload ./onboarding.pdf --collection handbook
coffer knowledge upload ./notes.docx --collection handbook --directory onboarding
```

- Conversion covers pdf, docx, pptx, xlsx, html and more. An upload over the 20 MB ceiling is refused before anything is converted or written, and an unsupported type is refused by name.
- A converted document is indistinguishable from one you typed: same frontmatter, same audit event, same place in the tree.
- The description is optional input but never optional output. With no internal model connection configured, Coffer draws one from the document's own opening prose rather than leaving the catalogue entry blank.

## Finding things

Three motions, and you pick by what you already know:

```bash
coffer knowledge ls handbook/onboarding      # browse: folders and files, with descriptions
coffer knowledge grep "SO_REUSEADDR"         # every matching line, as path:line
coffer knowledge search "daemon port"        # the files that match, with the lines that matched
```

`ls` walks the catalogue one level at a time, so you choose a file from titles and descriptions. `grep` and `search` are the same matcher over the same files — ripgrep across every collection the caller may see — reported two ways: `grep` gives you every matching line, `search` gives you one result per file, with that file's title and description alongside the lines that matched. Reach for `search` when you want the file rather than the line.

Matching is literal: a regular expression, case sensitive. Give it a distinctive word or an exact phrase, not a question in your own words — there is no ranking, no scoring and no modes to choose between. What comes back is the files that contain what you typed.

## The tidy pass

A collection accumulates the way notes do: the same fact written twice from two sessions, one file that grew until it covers four subjects. Nothing about that is wrong at write time, which is why writing stays dumb. The tidying is deferred to a **tidy pass** — a bounded agentic rewrite that reads a collection's files and merges duplicates, splits an overgrown file, and gives each one a title and description that earn it.

The pass needs an internal model connection; with none configured it does nothing at all, cleanly. A background sweep runs it on an interval, and it is off until an operator switches it on — an unattended rewriter should be something you turned on, never something you discover running. In a vault that spans machines the sweep runs on exactly one of them, because two machines merging the same files produce two different documents that git would merge as two additions.

`.history/` is the entire safety net. Every tool the pass uses archives a file's prior revision before overwriting or retiring it, so a rewrite is always recoverable — there is no diff to approve before a pass lands.

Run one by hand whenever you want:

```bash
coffer knowledge organize handbook
```

The collection's page in the web UI has a **Tidy** button that does the same thing.

## The CLI

Everything above lives under one group, `coffer knowledge`:

| Area        | Commands                        |
| ----------- | ------------------------------- |
| Collections | `collections` · `create`        |
| Files       | `ls` · `read` · `write` · `delete` · `upload` |
| Retrieval   | `grep` · `search`               |
| Tidy        | `organize`                      |

Deleting a collection is a Resource operation: `coffer resource delete knowledge:<name>`.

## The REST surface

The daemon serves knowledge under `/api/v1/knowledge`. These routes are the *user's* surface and therefore unscoped — per-agent authorization governs what an agent sees through the MCP tools, not what the person who owns the vault sees in their own UI.

| Route                                             | Purpose                                     |
| ------------------------------------------------- | ------------------------------------------- |
| `GET`/`POST` `/api/v1/knowledge/collections`      | List collections; create one.               |
| `GET` `/api/v1/knowledge/tree?path=…`             | One level of the catalogue.                 |
| `GET`/`PUT`/`DELETE` `/api/v1/knowledge/file`     | Read, write or delete one file.             |
| `GET` `/api/v1/knowledge/grep`                    | Matching lines.                             |
| `POST` `/api/v1/knowledge/search`                 | Matching files, with their matched lines.   |
| `POST` `/api/v1/knowledge/upload`                 | Convert a document and file it.             |
| `POST` `/api/v1/knowledge/collections/{name}/tidy` | Run the tidy pass now.                     |

A search answers with `{"results": [{path, title, description, lines: [{line_number, line}]}]}` — the files, and what matched in each.

Deleting a whole collection goes through the kind-agnostic resource route, `DELETE /api/v1/resources/knowledge/{name}` — there is no `DELETE /api/v1/knowledge/collections/{name}`.

## The MCP tools

Every connected MCP client gets six built-in knowledge tools. None of them takes a **scope**: a call spans every collection the calling agent is authorized for, and the gateway supplies that identity at session handshake. `coffer__grep` and `coffer__search` accept an optional `collection` to *narrow* a call to one of those collections when the agent already knows where to look — it can never reach one the agent was not authorized for.

| Tool             | What it does                                                                    |
| ---------------- | ------------------------------------------------------------------------------- |
| `coffer__list`   | The collections you may read, or one level of the catalogue under a path.        |
| `coffer__grep`   | Every line matching a pattern, with its file and line number.                    |
| `coffer__search` | The files matching a word or phrase, each with its title, description and lines. |
| `coffer__read`   | One file in full, by path.                                                       |
| `coffer__write`  | Create a file in a collection or folder, or replace one at a path.               |
| `coffer__delete` | Remove one file, and the `.raw/` original behind it if it had one.               |

The motion they are shaped around is **catalogue, then grep**: `list` to choose which file, `grep` to find which line, `search` for when you cannot afford to browse first. They are deliberately not modes of one tool — an agent picks by what it knows, not by a flag.

Agents both read and write here: a file one agent records is what the next agent finds, which is the point of keeping it in Coffer rather than in any single agent's own store.

## In the web UI

Knowledge is one page under **Resources**. `/knowledge` lists your collections with a description and a file count, and **New collection** creates one. `/knowledge/:collection` opens one collection: a folder tree you walk a level at a time with a filter box that matches names as you type, the selected file rendered beside it, a search box over that collection, and two buttons — **Upload** to convert a document into the tree, **Tidy** to run the tidy pass on demand.

[Memory →](/guide/memory)
