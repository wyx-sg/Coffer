"""Vault sync domain (spec vault-sync; ADR
sync-applies-clean-merges-and-stops-on-any-conflict).

Pure value objects: the one remote, a round's record, a stop and its answers,
a join's preview, the deletion breaker's arithmetic, and a machine's
descriptor. No filesystem, no git — those live in infrastructure.
"""
