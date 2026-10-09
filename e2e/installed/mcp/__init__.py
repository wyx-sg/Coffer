"""Installed-build MCP acceptance (``make verify-installed-mcp OUT=...``).

The repository's tiers test this checkout in-process; this suite drives an
installed Coffer from outside — real HTTP ``/mcp`` with its notification stream,
the official MCP SDK over Streamable HTTP and over the installed stdio shim —
against synthetic upstreams (``upstream.py``) whose ledgers count what really
reached them. See .agents/testing.md "Installed-build Acceptance".
"""
