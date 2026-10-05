## Decisions

### A dialog, not a split pane

A config file is one JSON, TOML or Markdown file, and the tab is a list of at
most five entries plus subagent files. By the house rule a single file opens as
a dialog over the list (as a direct MCP entry's JSON and a plugin's details
already do); the tab keeps its rows. The dialog body is `ReadOnlyFile`, the
viewer the native memory store, unmanaged skill files and skill folders use,
so a file reads the same wherever it is opened.

### Show the file as written

The preview shows the file's own text, values included. The file is the
person's, on their own machine, readable by them in any editor; the daemon
listens on loopback only and shows it to the same person. Hiding values would
make the preview disagree with the file it claims to show.

### Addressing

Keys only, as before #534: `spec_for` refuses an unknown key before any read.
Under a directory entry the child must be a relpath the listing itself
returns (the listing already skips symlinks and non-`.md` files), so no
separate traversal or containment check is needed. A file not created yet is
`404 NOT_FOUND`, as the native-memory reader answers; the row offers no
preview for it.

### No fingerprint, no audit

The preview writes nothing. Like the native memory reader it carries no
fingerprint and records no audit event (workspace listings and reads audit
nothing, "Audit every agent lifecycle event").
