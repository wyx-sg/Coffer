"""A seeded generator of strings a Python regex matches, for tests.

It walks ``re._parser.parse(pattern.pattern, pattern.flags)`` and builds one
match, preferring alphanumerics so a generated secret has the entropy a real
one does. It exists so the bundled plaintext-secret rules can be tested with
a sample for every rule that never lives in the repository: the sample is
built in memory, and the repository's own secret scan has nothing to flag.

``re._parser`` is private; this module is test-only and the Python minor
version is pinned.

Not handled (the caller falls back to a hand-written sample): look-arounds
are ignored rather than satisfied, so a pattern that needs one to hold can
produce a string it does not match; the test checks the sample against the
real detector either way.
"""

from __future__ import annotations

import random
import re
import string
from dataclasses import dataclass, field

# The private parser's names; ``re._constants`` holds the opcodes.
from re import _constants as _c  # type: ignore[attr-defined]
from re import _parser  # type: ignore[attr-defined]
from typing import Any

_ALNUM = string.ascii_letters + string.digits
_PRINTABLE = [chr(i) for i in range(32, 127)] + ["\t", "\n"]
#: How far past its minimum an unbounded or wide repeat may run.
_EXTRA = 12

_CATEGORY_TESTS = {
    "CATEGORY_DIGIT": lambda ch: ch.isdigit() and ch.isascii(),
    "CATEGORY_NOT_DIGIT": lambda ch: not (ch.isdigit() and ch.isascii()),
    "CATEGORY_WORD": lambda ch: (ch.isalnum() and ch.isascii()) or ch == "_",
    "CATEGORY_NOT_WORD": lambda ch: not ((ch.isalnum() and ch.isascii()) or ch == "_"),
    "CATEGORY_SPACE": lambda ch: ch in " \t\n\r\f\v",
    "CATEGORY_NOT_SPACE": lambda ch: ch not in " \t\n\r\f\v",
}


@dataclass
class Sample:
    """A generated match: the text and where each capture group sits in it."""

    text: str
    #: Group number -> ``(start, end)`` in ``text``; absent when not taken.
    groups: dict[int, tuple[int, int]] = field(default_factory=dict)


class _Builder:
    def __init__(self, rng: random.Random, flags: int) -> None:
        self.rng = rng
        self.flags = flags
        self.parts: list[str] = []
        self.size = 0
        self.groups: dict[int, tuple[int, int]] = {}

    def emit(self, text: str) -> None:
        self.parts.append(text)
        self.size += len(text)

    def pick(self, candidates: list[str]) -> str:
        alnum = [c for c in candidates if c in _ALNUM]
        return self.rng.choice(alnum or candidates)

    def walk(self, items: _parser.SubPattern) -> None:
        for op, arg in items:
            self.node(op, arg)

    def count(self, low: int, high: int) -> int:
        top = high if high != _c.MAXREPEAT else low + _EXTRA
        return self.rng.randint(low, min(top, low + _EXTRA))

    def node(self, op: Any, arg: Any) -> None:
        rng = self.rng
        if op is _c.LITERAL:
            self.emit(chr(arg))
        elif op is _c.NOT_LITERAL:
            self.emit(self.pick([c for c in _PRINTABLE if c != chr(arg)]))
        elif op is _c.ANY:
            self.emit(self.pick([c for c in _PRINTABLE if c != "\n"]))
        elif op is _c.IN:
            self.emit(self.pick(_class_members(arg)))
        elif op is _c.CATEGORY:
            self.emit(self.pick(_class_members([(_c.CATEGORY, arg)])))
        elif op in (_c.MAX_REPEAT, _c.MIN_REPEAT, getattr(_c, "POSSESSIVE_REPEAT", None)):
            low, high, body = arg
            for _ in range(self.count(low, high)):
                self.walk(body)
        elif op is _c.SUBPATTERN:
            group, _add, _del, body = arg
            start = self.size
            self.walk(body)
            if group is not None:
                self.groups[group] = (start, self.size)
        elif op is getattr(_c, "ATOMIC_GROUP", None):
            self.walk(arg)
        elif op is _c.BRANCH:
            self.walk(rng.choice(arg[1]))
        elif op is _c.GROUPREF:
            start, end = self.groups.get(arg, (0, 0))
            self.emit("".join(self.parts)[start:end])
        # AT, ASSERT, ASSERT_NOT, GROUPREF_EXISTS: nothing to emit.


def _class_members(items: Any) -> list[str]:
    """The printable characters a bracket expression (or one category) holds."""
    negate = any(op is _c.NEGATE for op, _ in items)
    members: set[str] = set()
    for op, arg in items:
        if op is _c.LITERAL:
            members.add(chr(arg))
        elif op is _c.RANGE:
            low, high = arg
            members.update(chr(i) for i in range(low, min(high, 126) + 1) if i >= 9)
        elif op is _c.CATEGORY:
            test = _CATEGORY_TESTS[arg.name]
            members.update(c for c in _PRINTABLE if test(c))
    pool = [c for c in _PRINTABLE if (c in members) != negate]
    return pool or ["a"]


def generate(pattern: re.Pattern[str], rng: random.Random) -> Sample:
    """One string ``pattern`` is meant to match, with its capture groups."""
    tree = _parser.parse(pattern.pattern, pattern.flags)
    builder = _Builder(rng, pattern.flags)
    builder.walk(tree)
    return Sample("".join(builder.parts), dict(builder.groups))


def _find_group(items: _parser.SubPattern, number: int) -> _parser.SubPattern | None:
    for op, arg in items:
        if op is _c.SUBPATTERN:
            group, _add, _del, body = arg
            if group == number:
                return body
            found = _find_group(body, number)
            if found is not None:
                return found
        elif op in (_c.MAX_REPEAT, _c.MIN_REPEAT, getattr(_c, "POSSESSIVE_REPEAT", None)):
            found = _find_group(arg[2], number)
            if found is not None:
                return found
        elif op is _c.BRANCH:
            for branch in arg[1]:
                found = _find_group(branch, number)
                if found is not None:
                    return found
        elif op is getattr(_c, "ATOMIC_GROUP", None):
            found = _find_group(arg, number)
            if found is not None:
                return found
    return None


def min_width(pattern: re.Pattern[str], group: int = 0) -> int:
    """The fewest characters capture ``group`` (0: the whole match) can match."""
    tree = _parser.parse(pattern.pattern, pattern.flags)
    body = tree if group == 0 else _find_group(tree, group)
    return int(body.getwidth()[0]) if body is not None else 0
