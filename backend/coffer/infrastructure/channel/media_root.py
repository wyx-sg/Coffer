"""Where every channel saves the media it downloads.

One directory for all channels, in the ``content`` class (ADR
storage-is-five-classes-by-nature): the files are the user's only copy of what
someone sent the bot, so they are neither derived nor configuration, and they
are not synced. Resolved from ``HOME`` at every call, so a test's throwaway
home moves it too. The retention sweep ages files out of it one by one.
"""

from __future__ import annotations

import pathlib

from coffer.infrastructure.vault.home import content_root

#: The directory's name under ``content/``.
CHANNEL_MEDIA_DIR_NAME = "channel-media"


def default_media_dir() -> pathlib.Path:
    """``~/.coffer/content/channel-media``."""
    return content_root() / CHANNEL_MEDIA_DIR_NAME


__all__ = ["CHANNEL_MEDIA_DIR_NAME", "default_media_dir"]
