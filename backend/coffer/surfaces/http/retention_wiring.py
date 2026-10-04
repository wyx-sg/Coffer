"""The file retention policies bound at the composition root (attachments, skill data).

Each ``FilePolicy`` carries the sweeps and the preview count as closures over
the infrastructure file I/O, so the application ``RetentionService`` never
imports it (layered-architecture contract).
"""

from __future__ import annotations

from datetime import datetime

from coffer.application.retention_registry import FilePolicy
from coffer.domain.retention import (
    DEFAULT_ATTACHMENT_RETENTION_DAYS,
    DEFAULT_SKILL_DATA_RETENTION_DAYS,
)
from coffer.infrastructure.channel.seatalk_media import default_media_dir
from coffer.infrastructure.chat.media_store import FileChatMediaStore, default_chat_media_dir
from coffer.infrastructure.media_retention import (
    count_media_dir,
    count_media_tree,
    prune_media_dir,
    prune_media_tree,
)
from coffer.infrastructure.vault.home import skill_data_dir


def _channel_media_sweep(now: datetime, max_age_days: int) -> list[str]:
    """Prune ``~/.coffer/content/channel-media`` with the attachments window."""
    return prune_media_dir(default_media_dir(), max_age_days=max_age_days, now=now)


def _attachments_policy() -> FilePolicy:
    """The ``attachments`` retention policy over both media dirs: what a channel
    downloaded and what the web composer uploaded (spec resource-framework
    "Retain attachments on an adjustable policy")."""
    chat = FileChatMediaStore(default_chat_media_dir())

    def count(now: datetime, max_age_days: int) -> tuple[int, int]:
        c_total, c_old = count_media_dir(default_media_dir(), max_age_days=max_age_days, now=now)
        w_total, w_old = chat.count(now, max_age_days)
        return c_total + w_total, c_old + w_old

    return FilePolicy(
        name="attachments",
        display_name="Attachments",
        description="Files and images sent in conversations and channels.",
        default_retention_days=DEFAULT_ATTACHMENT_RETENTION_DAYS,
        sweeps=(_channel_media_sweep, chat.prune),
        count=count,
    )


def _skill_data_policy() -> FilePolicy:
    """The ``skill_data`` retention policy over ``~/.coffer/skill-data``: the logs,
    journals and temp files skill scripts write, one subfolder per skill (spec
    resource-framework "Retain skill working files on an adjustable policy")."""

    def sweep(now: datetime, max_age_days: int) -> list[str]:
        return prune_media_tree(skill_data_dir(), max_age_days=max_age_days, now=now)

    def count(now: datetime, max_age_days: int) -> tuple[int, int]:
        return count_media_tree(skill_data_dir(), max_age_days=max_age_days, now=now)

    return FilePolicy(
        name="skill_data",
        display_name="Skill working files",
        description="Logs, journals and temporary files skills write under ~/.coffer/skill-data.",
        default_retention_days=DEFAULT_SKILL_DATA_RETENTION_DAYS,
        sweeps=(sweep,),
        count=count,
    )


def build_file_policies() -> tuple[FilePolicy, ...]:
    """Every file policy the retention service sweeps, in the order they are listed."""
    return (_attachments_policy(), _skill_data_policy())
