"""Memory infrastructure (ADR keep-memory-in-one-place-agents-write-themselves).

``hub_store``
    ``vault/memory/``: its topic files read from disk, a person's edit written
    through the vault, a tidy kept as one commit, and an older build's hub
    entries converted once.
``repository``
    Which repository a directory belongs to (see "Identify a project by a key
    that does not depend on the machine").
``legacy``
    Removing what an older build wrote into the agents' own memory.
``frontmatter``
    The YAML fence the files here go through.
"""
