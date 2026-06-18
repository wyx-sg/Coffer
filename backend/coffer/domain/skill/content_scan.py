"""Heuristic content scanner for a skill folder — trust layer level L2.

Coffer delivers skills but never runs them; the host agent does. So Coffer
cannot enforce a skill's runtime behavior — what it *can* do is make risk
legible at ingest/enable time. This module walks a skill folder's text files
and flags patterns commonly associated with abuse (remote code execution,
network egress, secret exfiltration, obfuscation) so a user can review before
enabling the skill for an agent.

The scan is **heuristic and non-authoritative**: a finding is a warning to be
reviewed, not proof of malice, and a clean report is not a safety guarantee.
The known-evasion reality (a payload can be split, encoded, or staged at
runtime) is why findings warn rather than block by default — see ADR-027.

Purity: like ``validator.py`` this module reads the filesystem to inspect a
folder, but it imports nothing from infrastructure/surfaces (stdlib + enum +
dataclasses only), so it satisfies the domain-layer import contract.
"""

from __future__ import annotations

import os
import pathlib
import re
from dataclasses import dataclass
from enum import StrEnum

# Bump when the rules below change in a way that should invalidate a stored
# verdict (so a re-scan is known to be needed). Persisted on the skill config.
RULESET_VERSION = "1"

# Per-file byte cap: scanning a huge generated/data file is pointless and slow.
# Files larger than this are skipped (and noted as such is unnecessary — large
# data blobs are not where a hand-authored payload hides).
_PER_FILE_LIMIT_BYTES = 1_000_000

# Cap the number of findings so a pathological file can't produce a giant
# report; the verdict is still computed from everything scanned.
_MAX_FINDINGS = 100


class Severity(StrEnum):
    """Ordered severity for a single finding and for the overall verdict."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


_RANK: dict[Severity, int] = {
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}

# The verdict at or above which Coffer requires an explicit risk
# acknowledgment before a skill may be enabled for an agent (FR-029).
ACK_THRESHOLD = Severity.HIGH


def verdict_requires_ack(verdict: str | None) -> bool:
    """Whether a persisted verdict string gates enabling a skill (FR-029).

    Tolerant of ``None`` and of an unknown string (treated as not gating) so a
    stored value from a future ruleset never hard-fails the enable path.
    """
    if verdict is None:
        return False
    try:
        severity = Severity(verdict)
    except ValueError:
        return False
    return _RANK[severity] >= _RANK[ACK_THRESHOLD]


@dataclass(frozen=True)
class Finding:
    """One flagged line in one file (path is folder-relative, POSIX style)."""

    severity: Severity
    rule_id: str
    file: str
    line: int
    message: str


@dataclass(frozen=True)
class ScanReport:
    """Result of scanning a skill folder."""

    findings: tuple[Finding, ...]
    verdict: Severity | None
    ruleset_version: str
    truncated: bool

    @property
    def requires_acknowledgment(self) -> bool:
        """True when the verdict is severe enough to gate enabling (FR-029)."""
        return self.verdict is not None and _RANK[self.verdict] >= _RANK[ACK_THRESHOLD]


@dataclass(frozen=True)
class _Rule:
    rule_id: str
    severity: Severity
    pattern: re.Pattern[str]
    message: str


# Heuristic rules. Kept deliberately small and defensible to bound false
# positives; each is a single-line regex applied to decoded text. Ordered
# roughly by severity for readability only (evaluation order is irrelevant).
_RULES: tuple[_Rule, ...] = (
    _Rule(
        "remote_exec_pipe",
        Severity.CRITICAL,
        re.compile(r"\b(?:curl|wget)\b[^\n|]*\|\s*(?:sudo\s+)?(?:ba|z|k)?sh\b"),
        "Pipes a download directly into a shell (remote code execution).",
    ),
    _Rule(
        "base64_exec",
        Severity.CRITICAL,
        re.compile(
            r"base64\s+(?:--decode|-d|-D)\b[^\n|]*\|\s*(?:ba|z|k)?sh\b"
            r"|\bexec\s*\(\s*base64",
        ),
        "Decodes base64 content and executes it (obfuscated payload).",
    ),
    _Rule(
        "secret_access",
        Severity.HIGH,
        re.compile(
            r"(?:~|\$HOME)/\.(?:ssh|aws|gnupg)\b"
            r"|/\.aws/credentials\b|\bid_rsa\b|\.netrc\b|/etc/(?:passwd|shadow)\b"
            r"|\bAWS_SECRET_ACCESS_KEY\b",
        ),
        "References credential or secret material (possible exfiltration).",
    ),
    _Rule(
        "dangerous_rm",
        Severity.HIGH,
        re.compile(r"\brm\s+-[a-z]*r[a-z]*f?\b\s*(?:/\s|/$|~|\$HOME|\*)"),
        "Recursive force-delete targeting home, root, or a glob.",
    ),
    _Rule(
        "shell_eval",
        Severity.HIGH,
        re.compile(r"\beval\s+[\"'`]?\$\(|\beval\s+[\"'`]\$\{"),
        "Evaluates dynamically constructed shell input.",
    ),
    _Rule(
        "network_egress",
        Severity.MEDIUM,
        re.compile(
            r"\b(?:curl|wget|nc|ncat|telnet|scp|sftp)\b"
            r"|\brequests\.(?:get|post|put|request)\b"
            r"|\burllib\.request\b|\bhttp\.client\b|\bsocket\.socket\b"
            r"|\bfetch\s*\(|\bXMLHttpRequest\b",
        ),
        "Makes an outbound network call.",
    ),
    _Rule(
        "privilege",
        Severity.MEDIUM,
        re.compile(r"\bsudo\b|\bchmod\s+[0-7]*\+?x\b|\bchmod\s+777\b"),
        "Escalates privilege or makes a file executable.",
    ),
    _Rule(
        "obfuscation",
        Severity.MEDIUM,
        re.compile(r"[A-Za-z0-9+/]{200,}={0,2}|(?:\\x[0-9a-fA-F]{2}){12,}"),
        "Long encoded blob (base64/hex) — possible hidden payload.",
    ),
)

# Treat a file as binary (and skip scanning) if a chunk fails to decode or
# contains a NUL byte — mirrors the validator/file-viewer convention.
_NUL = b"\x00"


def scan_skill_folder(
    folder: pathlib.Path,
    *,
    per_file_limit_bytes: int = _PER_FILE_LIMIT_BYTES,
) -> ScanReport:
    """Walk a skill folder and return a heuristic risk report.

    Reads each in-folder text file (symlinks skipped — the validator already
    rejects path-escaping links) and applies the rule set line by line. The
    verdict is the worst severity found, or ``None`` when nothing is flagged.
    """
    findings: list[Finding] = []
    truncated = False

    for root, _dirnames, filenames in os.walk(folder, followlinks=False):
        root_path = pathlib.Path(root)
        for nm in sorted(filenames):
            entry = root_path / nm
            if entry.is_symlink() or not entry.is_file():
                continue
            try:
                if entry.stat().st_size > per_file_limit_bytes:
                    continue
                raw = entry.read_bytes()
            except OSError:
                continue
            if _NUL in raw:
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue

            rel = entry.relative_to(folder).as_posix()
            for lineno, line in enumerate(text.splitlines(), start=1):
                for rule in _RULES:
                    if rule.pattern.search(line):
                        findings.append(
                            Finding(rule.severity, rule.rule_id, rel, lineno, rule.message)
                        )
                        if len(findings) >= _MAX_FINDINGS:
                            truncated = True
                            break
                if truncated:
                    break
            if truncated:
                break
        if truncated:
            break

    verdict = _worst(findings)
    ordered = tuple(sorted(findings, key=lambda f: (-_RANK[f.severity], f.file, f.line, f.rule_id)))
    return ScanReport(
        findings=ordered,
        verdict=verdict,
        ruleset_version=RULESET_VERSION,
        truncated=truncated,
    )


def _worst(findings: list[Finding]) -> Severity | None:
    if not findings:
        return None
    return max((f.severity for f in findings), key=lambda s: _RANK[s])
