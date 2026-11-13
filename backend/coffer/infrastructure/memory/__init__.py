"""Memory infrastructure: the agents' memory files read, the hub kept, and
Coffer's own copies written into each agent (spec memory "Leave every memory an
agent wrote untouched").

The **readers** only read what Claude Code and Codex keep in their own memory
directories. The **writers** write only what is Coffer's there (the marked
block of a project's ``MEMORY.md``, Codex's ``extensions/coffer/``) and never
a file the agent wrote.

``readers``
    The two native-memory adapters, satisfying ``domain.memory.reader``.
``writers``
    The two writers, satisfying ``domain.memory.native_writer``.
``hub_store``
    ``vault/memory/``, read from disk and written through the vault (see "Keep
    every agent's memories in a hub in the vault").
``sync_ledger``
    ``local/memory-sync.json`` and the pending preview (see "Preview a first or
    large sync").
``repository`` and ``checkouts``
    Which repository a directory belongs to, and where each project is checked
    out on this machine (see "Identify a project by a key that does not depend
    on the machine", "Write a project's memories only where it is checked out").
``frontmatter``, ``native_files``
    The YAML fence and the atomic, backed-up writes the files here go through.
"""
