## MODIFIED Requirements

### Requirement: Present a collection as one tree in the web UI
The web UI MUST present a collection as **one tree** of its documents — no lanes, no tabs, no filter or retrieval box — with the chosen document in the pane beside it, the same two panes a skill's Files tab is. The tree MUST name every collection, folder and document by its name on disk: a collection has no title (see "Name a collection by its folder and edit its description in place"). The pane MUST render the document and offer **Edit**, which turns it into an editor saved through "Save a document edited in the web UI" and reports a conflict in place; open-in-external-editor and reveal-in-file-manager; and delete, naming the exact path before it runs, reporting a refusal in place, and leaving the preview on no file afterwards. The pane MUST show a document's title and description as read-only metadata above the editor, which holds only the body; a save refused as stale MUST say the document changed on disk and that the text was not saved, and offer **Reload**, **Compare** and **Copy my text**, never a second save over it. The tree MUST show the collection's `.inbox/` as an **Inbox** node carrying the number of items waiting; choosing it opens the Inbox view and expands the node to list the items, which open read-only, with no edit and no delete. That count MUST be the only signal of items waiting: the sidebar carries no badge for them. In the web UI inbox entries are called **items** (the spec's *material*), and curation is called **Curate** / **Curation** (整理) everywhere — the web UI, CLI help and docs-site — never "merge". The collection's header MUST carry one status line — *N documents · M waiting · curated <time>* — and Knowledge calls its files **documents** everywhere (memory keeps *notes*). The page MUST offer upload into the collection in view and **Add a document** (添加文档 — a title and body submitted as an item, see "Submit material through coffer__write"). The manual trigger MUST be a quiet **Curate now** in the Inbox view, in Recent changes and in the header's Automatic control, never on a document, reporting its progress (*Curating · 1 of 2*, no dialog), a pass already in flight and a failed pass. While Coffer's model is not set, the page MUST show no Inbox node, no Automatic control and no Curate now, and instead one line under the page title — set Coffer's model to curate new items into your documents — linking to Settings › General; items become documents as they arrive until then. The tree and the pane MUST extend to the bottom of the window and scroll inside.

#### Scenario: the viewer shows one tree of documents
- **GIVEN** a collection page whose tree holds a document at the root and one inside a folder, with one item of material waiting in the inbox
- **WHEN** the page renders, a document's row is clicked, and then the inbox item's
- **THEN** there is one tree — no lane headings, no tabs, no filter input — listing both documents and an `.inbox` folder holding the item
- **AND** the document offers Edit, open-in-editor, reveal and delete, and the inbox item offers neither Edit nor delete

#### Scenario: edit a document in place
- **GIVEN** a document open in a collection's pane
- **WHEN** the user chooses Edit, changes the text and saves
- **THEN** the save is sent with the fingerprint the pane loaded, and the pane renders the saved body

#### Scenario: the inbox node counts waiting items and holds the only trigger
- **GIVEN** a collection with two items waiting and Coffer's model set
- **WHEN** the collection page renders and the user opens the Inbox node
- **THEN** the node reads 2, the header reads *N documents · 2 waiting · curated <time>*, and Curate now is offered in the Inbox view and on no document or collection view

#### Scenario: no model shows no curation controls
- **GIVEN** Coffer's model not set
- **WHEN** a collection page renders
- **THEN** there is no Inbox node, no Automatic control and no Curate now, and one line links to Settings › General

#### Scenario: a stale save offers reload and compare
- **GIVEN** a document open in the editor that curation changes on disk before the user saves
- **WHEN** the user saves
- **THEN** the pane says the document changed on disk and the text was not saved, and offers Reload, Compare and Copy my text, with no way to save over it

#### Scenario: add a document submits an item
- **GIVEN** a collection page
- **WHEN** the user chooses Add a document and submits a title and body
- **THEN** one item waits in the collection's inbox with actor `user`, and no document is created directly

#### Scenario: curation is called curate, never merge
- **GIVEN** the web UI in English and in 中文, and `coffer knowledge --help`
- **WHEN** every label, button and help line about curation is read
- **THEN** each says Curate or Curation (整理 in 中文) and none says merge, and inbox entries are called items
