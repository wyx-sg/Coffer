"""The vault as files (spec vault-storage).

Pure value objects and rules for the files under ``~/.coffer/vault/``: where
each kind of document lives, the resource document's shape, per-file format
versions and their upgrade chains, who wrote a commit, and what a validator
can say about a file. No filesystem and no git — those live in
``coffer.infrastructure.vault``.
"""
