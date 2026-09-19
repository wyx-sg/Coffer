"""``alembic.ini`` stays ASCII, because Alembic reads it in the locale encoding.

Alembic hands the file to ``ConfigParser.read(..., encoding="locale")``. PEP 686
keeps that sentinel outside UTF-8 mode on purpose, so neither the ``-X utf8``
the PyInstaller specs freeze in nor a ``PYTHONUTF8`` in the environment changes
how this one file is decoded. A daemon started without ``LANG``/``LC_CTYPE`` --
what the desktop shell, the Dock and launchd all do -- therefore reads it as
ASCII, and a single non-ASCII byte, even inside a comment, ends startup with a
``UnicodeDecodeError`` before the first migration runs.

Nothing in development or CI reproduces that: an unfrozen interpreter in the C
locale turns UTF-8 mode on by itself, decodes the file happily, and leaves the
break for whoever installs the build. Hence a byte-level assertion rather than
a test that tries to load the config under a stripped locale.
"""

from __future__ import annotations

import pathlib

import coffer

ALEMBIC_INI = (
    pathlib.Path(coffer.__file__).resolve().parent
    / "infrastructure/persistence/migrations/alembic.ini"
)


def test_alembic_ini_has_no_non_ascii_bytes() -> None:
    raw = ALEMBIC_INI.read_bytes()

    offenders = [(offset, byte) for offset, byte in enumerate(raw) if byte > 0x7F]

    assert not offenders, (
        f"{ALEMBIC_INI} carries non-ASCII bytes at offsets "
        f"{[offset for offset, _ in offenders]}; Alembic reads this file in the "
        "locale encoding, so they crash the frozen daemon on any machine whose "
        "environment has no UTF-8 locale. Rewrite the text in ASCII."
    )
