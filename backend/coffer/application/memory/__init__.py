"""Application layer for the memory sync (spec memory).

Each machine publishes what its agents wrote into the hub in the vault
(``sync_publish``) and writes the hub into each local agent's own memory
(``sync_write``); :class:`~coffer.application.memory.sync_service.MemorySyncService`
drives both, and ``sync_view`` answers the Memory page.
"""
