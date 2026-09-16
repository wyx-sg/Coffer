"""Knowledge infrastructure: the filesystem, and ripgrep over it.

No index and no embedding client — a directory and a search binary are the
whole substrate (ADR knowledge-is-plain-files). The one thing on top is
``converters/``, which turns an uploaded document into the markdown that then
lands in that directory like any hand-written file.
"""
