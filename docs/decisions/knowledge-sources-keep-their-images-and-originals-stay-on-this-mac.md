# Knowledge Sources Keep Their Images; Originals Stay on This Mac

**Status**: Accepted
**Date**: 2026-10-12
**Deciders**: Yuxing Wu
**Related**: [Knowledge Is a Wiki of Pages Compiled From Kept Sources](knowledge-is-a-wiki-of-pages-compiled-from-kept-sources.md); [Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md); [Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy](storage-is-five-classes-by-nature.md); [Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](every-vault-write-is-a-validated-commit-naming-its-writer.md); [The Loopback Daemon Performs OS File Actions for the UI](daemon-proxies-os-file-actions.md); [Coffer Ships Its Own Manual as a Skill Resource](coffer-ships-its-own-skill.md); spec knowledge "Keep every upload as a Markdown source", "Keep the pictures of an upload beside its source", "Keep an upload's original on this Mac only"; OpenSpec change `keep-upload-pictures-and-originals`

## Context

An upload becomes a source: the converted Markdown with frontmatter under the
collection's `sources/`
([Knowledge Is a Wiki of Pages Compiled From Kept Sources](knowledge-is-a-wiki-of-pages-compiled-from-kept-sources.md)).
Until now that was all Coffer kept. MarkItDown was run without its picture
options, so every picture in a PDF, a slide deck or a Word document was
dropped, and the uploaded file itself was thrown away once converted.

Two things went missing with them:

- **Pictures carry meaning.** An architecture diagram, a flow chart, a
  screenshot of an error, a table pasted as an image: in design docs and slide
  decks these are often the point, and the text around them ("see the flow
  below") is meaningless without them. Agents that read Markdown can open a
  picture it links, and a person reading the source on the Knowledge page
  expects to see it.
- **The person sometimes wants the original layout.** A conversion flattens
  slides, columns and tables. Checking what a conversion lost, or just looking
  at the deck as it was presented, needs the file itself.

The forces on the answer:

- **The vault is a git repository that syncs.** Everything under
  `vault/knowledge/` is committed and pushed to the person's other Macs, and
  git keeps every blob forever. A 30 MB PDF committed once is carried by every
  clone for good, even after the source is deleted.
- **Hidden entries under `knowledge/` are not committed.** The vault's
  `.git/info/exclude` leaves out every dot-prefixed entry, so anything meant to
  sync and keep history must sit in a visible folder.
- **Agents read the Markdown, not the binary.** An agent gets nothing more out
  of a PDF or a `pptx` than the converted Markdown already gives it; the
  original is for the person's eyes.
- **Most embedded pictures are decoration.** Bullets, rules, icons, a logo on
  every slide. Kept naively, they would outnumber the pictures that matter and
  bloat the repository for nothing.

### How comparable products handle it

- **Karpathy's "LLM Wiki"** (the pattern the wiki follows) keeps clipped
  sources as Markdown with their images downloaded locally beside them, for
  example with Obsidian Web Clipper's "download attachments", so the LLM can
  view the pictures a source refers to.
- **Obsidian** keeps attachments as ordinary files in the vault, in an
  attachments folder beside the notes or one the person names, linked from the
  Markdown by relative path.
- **Notion** import uploads a document's images alongside the pages it
  creates; the imported file itself is not kept.
- **Logseq** keeps pasted and imported pictures in an `assets/` folder at the
  graph's root, linked as `../assets/<name>`.
- **MarkItDown** can inline a document's pictures as `data:` URIs
  (`keep_data_uris`), which is what Coffer now asks it for, but it reads no
  pictures out of a PDF.
- **Docling** and **Marker** extract a document's images to files and
  reference them from the Markdown they produce.

The common pattern: **pictures become files beside the Markdown, linked by
relative path**; the **original document is usually not kept** by the tool
that converted it, and where it is, it is an attachment like any other.

## Options Considered

### Option A — Take the pictures out into the collection, beside the source (chosen, with C)

The converter takes the pictures out of an upload: from an Office or HTML
document through MarkItDown's inlined `data:` URIs, and from a PDF by reading
the images on each page with pdfminer, listed after the text under
`## Images` with a `Page N:` heading each. What is kept is bounded:

- a picture under 48 pixels on a side is a decoration and is dropped;
- a picture over 5 MB is dropped;
- a repeat of one already kept (the same bytes, a logo on every slide) is kept
  once, and every place it appeared links the one file;
- no upload keeps more than 40;
- a format a browser cannot show (TIFF, BMP, EMF and the like) is re-encoded
  as PNG.

The pictures land at `<collection>/assets/<title-slug>-<first 8 hex of the
upload's SHA-256>/image-N.ext`, in the same commit as the source, and the
source links each one relatively, `../assets/<folder>/image-1.png`, so any
Markdown reader, an agent's included, follows it. `assets/` is a visible folder
on purpose: the vault leaves hidden knowledge entries out of git, and the
pictures must sync and keep their history like the Markdown that links them.
The sweep never files anything out of `assets/`.

- Pro: the meaning a diagram or screenshot carries survives the upload, on
  every Mac, for people and agents alike. Plain files with relative links, the
  layout Obsidian and Logseq use, so a collection opened in Obsidian shows them
  too.
- Pro: one commit holds the source and its pictures, so an Undo or a history
  restore treats them as one change.
- Pro: once decorations and repeats are dropped, what is left is small: a
  handful of diagrams per deck, typically tens to a few hundred kilobytes.
- Con: the vault grows with every upload that has pictures, and git keeps
  them after the source is deleted.
- Con: deleting a source leaves its `assets/` folder behind as orphans. Coffer
  does not clean them up; a later tidy could flag a folder no source links.
- Con: a picture that carries text (a scanned page, a table pasted as an image)
  is kept as a picture, not read; Coffer runs no OCR.

### Option B — Keep the uploaded file in the vault, synced

Store the original beside the source, say `assets/<folder>/original.pdf`,
committed and synced like everything else.

- Pro: the original layout is one click away on every Mac, and a bad
  conversion can always be checked against the file.
- Con: originals are the large part. A slide deck or a scanned PDF is
  routinely 10 to 50 MB, git stores every one forever, and each new Mac clones
  them all. The sync repository would grow by the size of every document ever
  uploaded, deleted or not.
- Con: it buys agents nothing: they read the Markdown and the pictures, and a
  PDF is no easier for them to read than its conversion.
- Why it lost: it puts the heaviest, least-read bytes into the one store that
  can never shed them.

### Option C — Keep the uploaded file on the uploading Mac only, never synced (chosen, with A)

Keep the uploaded bytes in the machine-local class, at
`~/.coffer/local/knowledge-originals/<sha256><.ext>`, mode `0600`, kept once
per content however often it is uploaded. The source's frontmatter records
`original: <file name>` and `original_sha256: <hex>`, written by Coffer, so
every Mac knows an original exists and which one it is. A source's read answers
`original` (its name, empty when there is none) and `original_path` (the
absolute path on this Mac, or null when it was uploaded on another). The
Knowledge page offers it under the source's title as **Original <name>**, the
name a button that opens the file in the Mac's default app through the
daemon's `/fs/open`; on another Mac it says the original is on the Mac it was
uploaded from. A Markdown or text upload is its own source, so it keeps no
original and gets no such keys.

- Pro: the person can look at the deck or PDF as it was, at no cost to the
  vault or to sync.
- Pro: naming the file by its hash makes keeping it idempotent and lets a
  restored source find its original again.
- Con: the original is lost if that Mac is lost; the Markdown and the pictures
  survive on every other Mac and in the remote.
- Con: nothing deletes an original when its source goes, so originals of
  deleted sources stay on disk. It is the person's own file, and a source
  brought back by Undo or a history restore finds it again; a later clean-up
  could offer to remove the unreferenced ones.
- Con: on any Mac but the one that uploaded it, the original is only named.

### Option D — Markdown only (the design this replaces)

Keep the converted Markdown and nothing else.

- Pro: the smallest vault and the simplest model: a collection is one tree of
  Markdown.
- Con: every diagram and screenshot is lost at upload, with nothing left to
  say it was there, and the person must keep the original themselves to see
  the layout or check a conversion.
- Why it lost: it throws away exactly what the person and agents found they
  needed.

## Decision

**A + C.** An upload's pictures are taken out, filtered and kept as ordinary
files of the collection under `assets/<title-slug>-<hash>/`, committed with the
source and linked from it by relative path, so they sync and keep history. The
uploaded file itself is kept on the Mac that uploaded it only, under
`~/.coffer/local/knowledge-originals/`, and the source names it with `original`
and `original_sha256`.

Rules a future change must respect:

- **Originals never enter the vault.** No upload, sync or restore may commit
  an uploaded binary; the vault carries Markdown and the bounded pictures only.
- **Pictures live in `assets/`, visible.** Not a hidden folder, which git would
  never see, and never filed elsewhere by the sweep. A source links its
  pictures by relative path, never by an absolute path or a Coffer URL.
- **The bounds stay.** Decorations, oversize pictures and repeats are dropped
  and an upload keeps at most 40 pictures, so the vault grows by what carries
  meaning.
- **`original` and `original_sha256` are Coffer's.** The guide tells agents to
  leave them as they are; they describe a source rather than change what it
  says.
- **An image-only PDF is still refused.** Pictures are kept beside text, not
  instead of it: a document with no text layer is refused as before, because a
  source with nothing to read is not knowledge an agent can use.

## Consequences

- The vault grows with pictures. The bounds keep it to the pictures that carry
  meaning, but git keeps them for good, like any committed file.
- Deleting a source leaves its pictures under `assets/` as orphans, and its
  original on the uploading Mac. Neither is cleaned up automatically; a later
  tidy finding could flag an `assets/` folder no source links, and a later
  clean-up could offer to remove unreferenced originals.
- Losing the uploading Mac loses its originals. The Markdown and the pictures
  survive everywhere else.
- A scanned PDF is still refused (`scanned_pdf`): pictures do not make a
  source without text.
- The Knowledge page shows a picture a Markdown document links by relative path
  inline, fetched through `GET /api/v1/knowledge/asset` (which carries the
  daemon's token, so the page reads it as a data URL), and a picture opened
  from the tree shows the picture. The asset route serves `png`, `jpg`,
  `jpeg`, `gif`, `webp` and `svg` files up to 10 MB through the same path
  guard as a document read, linked folders included, and answers 404 for
  anything else.
- `GET /api/v1/knowledge/file` carries `original` and `original_path`.
- The `coffer-guide` manual explains `assets/` and tells agents to leave
  `original` and `original_sha256` alone.
- Enforcement: spec knowledge "Keep every upload as a Markdown source", "Keep
  the pictures of an upload beside its source", "Keep an upload's original on
  this Mac only"; `infrastructure/knowledge/converters/images.py` (extraction
  and bounds), `infrastructure/knowledge/assets.py` (layout, links and the read
  route's guard), `infrastructure/knowledge/originals.py` (the machine-local
  store), `application/knowledge/ingest.py`.
