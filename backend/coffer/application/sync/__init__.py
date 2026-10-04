"""Sync application layer (spec vault-sync): the thin round over the vault
repository (``round_*``), the service around it that the surfaces call, and
the worker that runs it on the remote's interval. Talks to git and files only
through ``round_ports`` and ``service_ports``."""
