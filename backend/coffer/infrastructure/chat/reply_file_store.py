"""The ``chat_reply_files`` rows: what each assistant reply changed in each file
(spec chat "Record what each reply changed in each file").

Beside ``persistence.py`` because it is one table with three reads and writes of
its own; ``MessageRepo`` delegates to it. The rows go with their reply by the
foreign key's ``ON DELETE CASCADE``, so a message, a conversation and a
retention prune each delete them without naming the table.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.domain.chat.reply_file import DiffOmitted, ReplyFile, ReplyFileSummary
from coffer.infrastructure.chat.persistence_models import ReplyFileModel


def _omitted(value: str | None) -> DiffOmitted | None:
    return "binary" if value == "binary" else "too_large" if value == "too_large" else None


def _distinct(files: Sequence[ReplyFile]) -> list[ReplyFile]:
    """The files with a repeated path dropped (the first wins): a path is the key."""
    by_path: dict[str, ReplyFile] = {}
    for f in files:
        by_path.setdefault(f.path, f)
    return list(by_path.values())


class ReplyFileStore:
    """SQLAlchemy reads and writes of ``chat_reply_files``; ``MessageRepo`` is one,
    which is how it satisfies the reply-file half of its port."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def record_files(self, message_id: str, files: Sequence[ReplyFile]) -> None:
        """Keep ``files`` as the reply's records, replacing any it had."""
        async with self._sm() as session:
            await session.execute(
                delete(ReplyFileModel).where(ReplyFileModel.message_id == message_id)
            )
            session.add_all(
                ReplyFileModel(
                    message_id=message_id,
                    path=f.path,
                    seq=seq,
                    added=f.added,
                    removed=f.removed,
                    diff=f.diff,
                    diff_omitted=f.diff_omitted,
                )
                for seq, f in enumerate(_distinct(files))
            )
            await session.commit()

    async def list_files(self, message_id: str) -> list[ReplyFileSummary]:
        """The reply's files in recorded order, without the diff text."""
        stmt = (
            select(
                ReplyFileModel.path,
                ReplyFileModel.added,
                ReplyFileModel.removed,
                ReplyFileModel.diff.is_not(None),
            )
            .where(ReplyFileModel.message_id == message_id)
            .order_by(ReplyFileModel.seq)
        )
        async with self._sm() as session:
            rows = (await session.execute(stmt)).all()
        return [
            ReplyFileSummary(path, added, removed, bool(has_diff))
            for path, added, removed, has_diff in rows
        ]

    async def get_file(self, message_id: str, path: str) -> ReplyFile | None:
        """One recorded file with its diff, or ``None``."""
        stmt = select(ReplyFileModel).where(
            ReplyFileModel.message_id == message_id, ReplyFileModel.path == path
        )
        async with self._sm() as session:
            row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return ReplyFile(row.path, row.added, row.removed, row.diff, _omitted(row.diff_omitted))
