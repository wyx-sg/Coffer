"""The one-time upgrade of a home to the vault layout (``coffer migrate``).

Only this package reads the previous layout — ``coffer.db``'s moved tables
and the trees at their old places — and only when a person runs the upgrade;
nothing else in the build keeps a reader for them. Its modules are imported
directly: the daemon needs only ``guard``, and must not load the exporters,
which read every kind's tables.
"""
