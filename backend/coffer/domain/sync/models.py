"""Export/import result value objects (spec 010).

Both operations report the same three things the spec asks for: how much of
each area moved, which individual resources could not be applied, and where
the bundle is. Per-resource failures are *reported* rather than fatal, so they
are part of a successful result, not an exception.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AreaCount:
    """How many items one bundle area holds after the operation."""

    area: str
    count: int


@dataclass
class ExportSummary:
    """Outcome of writing a bundle."""

    path: str
    #: Per-area counts, in a stable order (see ``BundlePort`` areas).
    areas: list[AreaCount] = field(default_factory=list)
    #: ``<kind>:<name>`` refs that could not be serialized, with the reason.
    failures: list[tuple[str, str]] = field(default_factory=list)
    #: Whether credential ciphertext was included (never the master key).
    credentials_included: bool = False


@dataclass
class ImportSummary:
    """Outcome of applying a bundle."""

    path: str
    areas: list[AreaCount] = field(default_factory=list)
    #: ``<kind>:<name>`` (or ``state/<area>/<doc>``) refs that could not be
    #: applied on this machine, with the reason. Never fatal.
    failures: list[tuple[str, str]] = field(default_factory=list)
    #: Credential refs whose ciphertext cannot be decrypted here — the master
    #: key has not been bootstrapped onto this machine yet.
    locked_refs: list[str] = field(default_factory=list)
