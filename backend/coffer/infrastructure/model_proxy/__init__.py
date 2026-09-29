"""The local model proxy: a separate loopback process, started from the daemon's
own binary, that relays Claude Code's and Codex's API-key traffic byte for byte
to the upstream it picks, injects the real key, reads usage from a copy of the
stream and fails over only before the first content byte (ADR
api-key-providers-are-reached-through-a-separate-local-model-proxy).

- :mod:`.app` — the raw ASGI app: Host/Origin refusal, token auth, routes.
- :mod:`.relay` — one request's attempts against upstream members.
- :mod:`.members` — member health, cooldowns and session affinity.
- :mod:`.spool` — usage records appended to spool files the daemon ingests.
- :mod:`.info` — ``~/.coffer/proxy.json``, how a daemon finds a running proxy.
- :mod:`.entry` — ``coffer-daemon proxy`` / ``python -m …model_proxy.entry``.
- :mod:`.supervisor` — the daemon's side: spawn, re-attach, push state, restart.
"""
