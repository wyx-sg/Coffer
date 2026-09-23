"""Memory infrastructure: the agents' files read, and Coffer's own files written.

Two halves, and the boundary between them is the layer's whole prohibition (spec
memory "Never write an agent's native memory"). The **readers** only read: they
list and parse what Claude Code and Codex already keep in their own memory
directories and write nothing there, ever. Everything else here writes only
Coffer's own derived tree under ``~/.coffer/memory/``, which may be deleted and
rebuilt at any time (see "Keep the memory tree derived and local").

The modules, and which pass owns which:

``paths``
    The sole owner of path construction, and the traversal guard (see "Confine
    reads to registered agents' memory paths").
``repository``
    Which repository a directory belongs to — walking up to ``.git``, following
    a worktree's pointer to the main checkout, reading ``origin`` out of the
    config. This is what collapses a worktree, a second clone and the main
    checkout into one partition (see "Identify a partition by its repository"),
    and what answers ``None`` for a directory that is in no repository at all
    (see "Create no partition for a non-repository directory").
``frontmatter``
    The YAML fence and the atomic write every file here goes through.
``store``
    A partition's ``MEMORY.md``, ``notes/``, ``RETIRED.md`` and ``.raw/``, with
    one writer each — aggregation writes ``.raw/`` and nothing else touches it
    (see "Keep distil out of the raw directory").
``source_state``
    The per-source digest cache that lets an unchanged source be skipped without
    re-parsing (see "Skip unchanged sources").
``files``
    The read-only file tree behind the partition's own browse-and-preview
    surface (see "Present partitions as a table and a file tree").
``readers``
    The two native-memory adapters, satisfying ``domain.memory.reader``.
``delivery``
    Per-agent session-start hook installation — which event, which settings
    file, which marker (see "Install delivery hooks explicitly and removably").
    An agent's *settings* are not its memory, and that distinction is the only
    reason writing there is allowed at all.
"""
