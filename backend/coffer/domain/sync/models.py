"""What one serialization of the vault reports (spec vault-sync).

Step 1 of a converge round writes the vault into the working tree and reports
how much of each area it wrote and which individual resources it could not
render. Per-resource failures are *reported* rather than fatal, so they are
part of a successful result, not an exception — and the exporter protects
their paths so a row it could not render is never published as a deletion.
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
