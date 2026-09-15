// frontend/src/components/filePane.ts
//
// One height for every pane that browses files: the five file trees (skill,
// knowledge, memory partition, an agent's memory store, an agent's config
// files) and the read-only viewers beside them.
//
// It is a shared constant rather than five literals because the number is not
// a local styling choice — it is the answer to "how far down the page may this
// column push everything below it", and the two columns sitting side by side
// have to agree or one of them scrolls while the other drags the page. They
// had drifted already: the viewers capped at 60vh, knowledge's preview at
// 70vh, and no tree capped at all, so a collection with a few hundred notes
// grew a list the page could only be scrolled past.
//
// `vh` rather than a fixed height: the pane should use the window the reader
// actually has. 60 leaves room for the page header and the row of actions
// above it without the pane's own scrollbar starting immediately.
export const FILE_PANE_MAX_HEIGHT = "max-h-[60vh] overflow-auto";
