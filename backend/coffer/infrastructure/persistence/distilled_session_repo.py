"""SQLAlchemy ledger repo for the auto-distill catch-up sweep (Spec 007 FR-046).

Records which ``(agent_name, session_id, content_sha256)`` triples have already
been distilled into the journal lane so the sweep never double-distills a settled
session. Kept in its own module (mirroring ``retention_repo``) to stay within the
file-size budget.
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy.exc
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.infrastructure.persistence.models import DistilledSessionModel


class DistilledSessionRepo:
    """Concrete idempotency-ledger repo against the ``distilled_sessions`` table."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def is_distilled(self, agent_name: str, session_id: str, content_sha256: str) -> bool:
        async with self._sm() as session:
            stmt = select(DistilledSessionModel.id).where(
                DistilledSessionModel.agent_name == agent_name,
                DistilledSessionModel.session_id == session_id,
                DistilledSessionModel.content_sha256 == content_sha256,
            )
            row = (await session.execute(stmt)).first()
            return row is not None

    async def distilled_session_ids(self, agent_name: str) -> set[str]:
        """All session ids for *agent_name* that have at least one ledger row
        (any sha). One indexed query — lets a list view mark each row
        done/never without reading transcript files on every poll."""
        async with self._sm() as session:
            stmt = select(DistilledSessionModel.session_id).where(
                DistilledSessionModel.agent_name == agent_name
            )
            return {row[0] for row in (await session.execute(stmt)).all()}

    async def mark_distilled(
        self,
        agent_name: str,
        session_id: str,
        content_sha256: str,
        distilled_at: datetime,
    ) -> None:
        """Idempotent insert: a duplicate ``(agent, session, sha)`` is a no-op."""
        async with self._sm() as session:
            session.add(
                DistilledSessionModel(
                    agent_name=agent_name,
                    session_id=session_id,
                    content_sha256=content_sha256,
                    distilled_at=distilled_at,
                )
            )
            try:
                await session.commit()
            except sqlalchemy.exc.IntegrityError:
                # The unique constraint already holds this triple — nothing to do.
                await session.rollback()
