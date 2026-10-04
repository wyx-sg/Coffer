"""One-time removal of state earlier builds kept for the agent layer.

Earlier builds parsed the agents' ``.jsonl`` transcripts and remembered the
result in ``~/.coffer/derived/cache/agent/.transcript_summaries.json``. Sessions
are now listed by the agents themselves (spec agent-registry
"List an agent's native sessions through the agent"), so nothing reads or
writes that directory any more. It is
derived state, so deleting it loses nothing; this removes the leftover at
startup. Idempotent, and a failure is only logged: a stale cache file is not a
reason to stop the daemon.
"""

from __future__ import annotations

import logging
import shutil

from coffer.infrastructure.vault.home import derived_root

log = logging.getLogger(__name__)


def remove_transcript_sidecar() -> None:
    """Delete ``derived/cache/agent`` (blocking; run it in a thread)."""
    legacy = derived_root() / "cache" / "agent"
    try:
        if legacy.is_dir():
            shutil.rmtree(legacy)
            log.info("agent.legacy_transcript_cache.removed")
    except OSError:
        log.warning("agent.legacy_transcript_cache.remove_failed", exc_info=True)
