"""Sync application layer (spec vault-sync): the converge round, the service
that owns the remote and the lock, and the serializer and appliers the round
drives in each direction. Talks to the filesystem, git and credentials only
through the ports in ``ports.py``."""
