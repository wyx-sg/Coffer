"""A text with every plaintext value masked (spec vault-sync "Show a plaintext
finding in its file").

The Sync page shows a person the lines around a finding so they can judge
whether it is a secret, without Coffer handing the value out. The values are
the detector's (spec secret "Detect plaintext secrets with the bundled
rules"), found on the whole file, so a value a rule reads across lines (a
private-key block) is masked on each line it covers.

Each value's shape is worked out from the whole value, so a multi-line one is
described once; only its first line keeps a public prefix.
"""

from __future__ import annotations

from dataclasses import replace

from coffer.domain.plaintext_shape import MaskedValue, mask, shape_of, split_rows
from coffer.infrastructure.secret.detector import Lines, by_line, detect


def find_text(text: str, path: str = "") -> list[tuple[int, str, str]]:
    """``(line, key, rule)`` for each plaintext value in ``text``; the key is
    the name the value is assigned to, or the rule's id when it has none."""
    return [(n, d.key or d.rule, d.rule) for n, d in by_line(text, detect(text, path))]


def mask_text(text: str, path: str = "") -> list[tuple[str, tuple[MaskedValue, ...]]]:
    """One ``(masked line, values on it)`` per row of ``text`` (see
    :func:`split_rows`). A masked line keeps its row's length; the values
    themselves are not returned."""
    rows = split_rows(text)
    masked = list(rows)
    values: list[list[MaskedValue]] = [[] for _ in rows]
    lines = Lines(text)
    for d in detect(text, path):
        value = text[d.start : d.end]
        shape = shape_of(value)
        hidden = mask(value, shape)
        key = d.key or d.rule
        used = 0
        for n, c0, c1 in lines.segments(d.start, d.end):
            width = c1 - c0
            i = n - 1
            if i >= len(rows) or c1 > len(rows[i]):
                used += width + 1
                continue
            masked[i] = masked[i][:c0] + hidden[used : used + width] + masked[i][c1:]
            values[i].append(
                MaskedValue(
                    c0, c1, key, d.rule, shape if used == 0 else replace(shape, prefix=None)
                )
            )
            used += width + 1
    return [
        (m, tuple(sorted(v, key=lambda x: x.start))) for m, v in zip(masked, values, strict=True)
    ]


__all__ = ["find_text", "mask_text"]
