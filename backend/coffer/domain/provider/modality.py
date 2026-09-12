"""``Modality`` — what KIND of model a curated entry names.

An endpoint serves more than chat: the same credential usually reaches an
embedding model, an image model, sometimes video or speech. A curated entry
therefore records which kind it is, so a picker asks for the kind it needs
instead of offering every id to every surface (a chat dropdown narrows to
``text``; the global embedding setting narrows to ``embedding``).

The stored modality is the TRUTH. :func:`infer_modality` exists for the two
moments where nobody has said yet — the one-shot migration that converted the
plain-string sets, and endpoint introspection, which pre-fills a value the user
then corrects. Nothing infers at load time: a stored entry is taken as written.
"""

from __future__ import annotations

import re
from enum import StrEnum


class Modality(StrEnum):
    """The kind of output a model produces."""

    TEXT = "text"
    EMBEDDING = "embedding"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


#: Substrings that are long enough to be unambiguous anywhere in an id.
_SUBSTRINGS: tuple[tuple[str, Modality], ...] = (
    ("embed", Modality.EMBEDDING),
    ("dall", Modality.IMAGE),
    ("imagen", Modality.IMAGE),
    ("image", Modality.IMAGE),
    ("flux", Modality.IMAGE),
    ("video", Modality.VIDEO),
    ("sora", Modality.VIDEO),
    ("whisper", Modality.AUDIO),
    ("audio", Modality.AUDIO),
)

#: Short names that MUST match a whole token — ``sd`` inside a longer word says
#: nothing, while ``sd``/``sd3``/``sdxl`` as a token of its own is Stable
#: Diffusion. A trailing version number is part of the token (``tts-1``,
#: ``veo3``), so the pattern allows digits and a letter suffix after the stem.
_TOKENS: tuple[tuple[re.Pattern[str], Modality], ...] = (
    (re.compile(r"^sd(\d.*|xl.*)?$"), Modality.IMAGE),
    (re.compile(r"^veo\d*$"), Modality.VIDEO),
    (re.compile(r"^tts\d*$"), Modality.AUDIO),
)

_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def infer_modality(model_id: str) -> Modality:
    """Guess a model id's modality from its name; ``text`` when nothing matches.

    A convenience for pre-filling, never a source of truth — vendors name models
    however they like, and the user corrects a wrong guess from the connection's
    model table.
    """
    name = model_id.strip().lower()
    for needle, modality in _SUBSTRINGS:
        if needle in name:
            return modality
    for token in _TOKEN_SPLIT.split(name):
        if not token:
            continue
        for pattern, modality in _TOKENS:
            if pattern.match(token):
                return modality
    return Modality.TEXT


__all__ = ["Modality", "infer_modality"]
