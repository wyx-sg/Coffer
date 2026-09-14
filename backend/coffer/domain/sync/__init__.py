"""Vault export/import domain (spec vault-sync, ADR: vault-sync).

Pure value objects and contracts: the bundle manifest, the export/import
summaries, deterministic resource serialization, path portability, and the
error family. No filesystem, no database — those live in infrastructure.
"""
