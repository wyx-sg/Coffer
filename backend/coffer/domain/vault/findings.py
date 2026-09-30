"""What validation can say about a vault file (spec vault-storage).

Every change to the vault — a person's, the daemon's, a merge's — passes one
validator before it is committed. A file that fails stays in the working tree,
uncommitted, and carries one or more **findings**; the effective version is
the one at ``HEAD`` until the file is fixed. A warning never stops a commit:
an unknown field is a warning because to an older build a newer build's field
and a typo look the same (ADR every-vault-file-carries-its-format-version).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    #: The file is not committed and does not take effect.
    ERROR = "error"
    #: The file is committed; the finding is reported beside it.
    WARNING = "warning"


class FindingCode(StrEnum):
    #: Not parseable as the document its path says it is.
    INVALID_DOCUMENT = "invalid_document"
    #: A required field is missing or has the wrong type.
    MISSING_FIELD = "missing_field"
    #: The document's ``kind`` disagrees with the directory it sits in.
    KIND_MISMATCH = "kind_mismatch"
    #: Another path already held this uid at ``HEAD``; this copy is the later one.
    DUPLICATE_UID = "duplicate_uid"
    #: Another resource of the same kind already has this name.
    NAME_TAKEN = "name_taken"
    #: The kind's own schema or validators refused the configuration.
    CONFIG_INVALID = "config_invalid"
    #: Written by a newer Coffer in a format this build cannot read.
    NEWER_FORMAT = "newer_format"
    #: Written by a newer Coffer; readable here, but read-only.
    NEWER_FORMAT_READ_ONLY = "newer_format_read_only"
    #: An edit to a file still waiting for its layout upgrade.
    OLDER_FORMAT_EDIT = "older_format_edit"
    #: A field this build does not know; kept, and reported.
    UNKNOWN_FIELD = "unknown_field"
    #: A value that looks like a secret in plain text.
    SECRET_IN_FILE = "secret_in_file"
    #: A reference (by uid) to a resource the vault does not hold.
    DANGLING_REFERENCE = "dangling_reference"


#: The codes that are warnings; every other code stops the commit.
WARNING_CODES = frozenset(
    {FindingCode.UNKNOWN_FIELD, FindingCode.NEWER_FORMAT_READ_ONLY, FindingCode.DANGLING_REFERENCE}
)


@dataclass(frozen=True)
class Finding:
    """One thing a validator says about one file."""

    path: str
    code: FindingCode
    message: str
    uid: str | None = None

    @property
    def severity(self) -> Severity:
        return Severity.WARNING if self.code in WARNING_CODES else Severity.ERROR

    @property
    def blocking(self) -> bool:
        return self.severity is Severity.ERROR


def blocking(findings: list[Finding] | tuple[Finding, ...]) -> list[Finding]:
    """The findings that keep a file out of the next commit."""
    return [f for f in findings if f.blocking]


__all__ = ["WARNING_CODES", "Finding", "FindingCode", "Severity", "blocking"]
