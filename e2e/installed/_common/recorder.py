"""Case results: ``cases.json`` and ``summary.md`` in the run's directory.

A case is PASS, FAIL, BLOCKED (could not be run here, with the reason) or N/A
(outside the current contract; recorded as an observation). Only PASS is a
pass: the run's exit code is non-zero when any case FAILs, and BLOCKED and N/A
are reported, never counted.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from e2e.installed._common.redact import Redactor

PASS, FAIL, BLOCKED, NA = "PASS", "FAIL", "BLOCKED", "N/A"
STATUSES = (PASS, FAIL, BLOCKED, NA)


@dataclass
class Case:
    id: str
    title: str
    area: str
    status: str
    expected: str
    actual: Any
    upstream_requests: Any
    evidence: str


class CaseRecorder:
    def __init__(self, out: Path, redactor: Redactor, suite: str) -> None:
        self._out = out
        self._redactor = redactor
        self.suite = suite
        self.cases: list[Case] = []
        self.area = ""

    def ids(self) -> set[str]:
        return {c.id for c in self.cases}

    def record(
        self,
        case_id: str,
        title: str,
        *,
        expected: str,
        actual: Any,
        ok: bool | None = None,
        status: str | None = None,
        upstream: Any = None,
        evidence: str = "transcript.jsonl",
    ) -> bool:
        """Record one case; returns whether it passed."""
        if case_id in self.ids():
            raise ValueError(f"case {case_id!r} recorded twice")
        final = status or (PASS if ok else FAIL)
        if final not in STATUSES:
            raise ValueError(f"unknown status {final}")
        self.cases.append(
            Case(
                case_id,
                title,
                self.area,
                final,
                expected,
                self._redactor.value(actual),
                upstream,
                evidence,
            )
        )
        print(f"{final:8} {case_id}  {title}", flush=True)
        self.write()
        return final == PASS

    def blocked(self, case_id: str, title: str, *, expected: str, reason: str) -> None:
        self.record(case_id, title, expected=expected, actual={"reason": reason}, status=BLOCKED)

    def missing(self, planned: list[tuple[str, str]], error: BaseException) -> None:
        """A phase stopped early: each planned case it never recorded is a FAIL."""
        for case_id, title in planned:
            if case_id not in self.ids():
                self.record(
                    case_id,
                    title,
                    expected="the case runs",
                    actual={"harness_error": f"{type(error).__name__}: {error}"},
                    status=FAIL,
                )

    def counts(self) -> dict[str, int]:
        return {s: sum(1 for c in self.cases if c.status == s) for s in STATUSES}

    def exit_code(self) -> int:
        return 1 if any(c.status == FAIL for c in self.cases) else 0

    def write(self, header: dict[str, Any] | None = None) -> None:
        doc = [asdict(c) for c in self.cases]
        (self._out / "cases.json").write_text(json.dumps(doc, indent=2, default=str))
        if header is not None:
            (self._out / "summary.md").write_text(self._redactor.text(self._summary(header)))

    def _summary(self, header: dict[str, Any]) -> str:
        counts = self.counts()
        lines = [
            f"# Installed-build acceptance: {self.suite}",
            "",
            *(f"- **{k}**: {v}" for k, v in header.items()),
            "",
            "| " + " | ".join(STATUSES) + " |",
            "| " + " | ".join("---" for _ in STATUSES) + " |",
            "| " + " | ".join(str(counts[s]) for s in STATUSES) + " |",
            "",
            "| Status | Case | Area | Title | Upstream |",
            "| --- | --- | --- | --- | --- |",
        ]
        for c in self.cases:
            upstream = "" if c.upstream_requests is None else str(c.upstream_requests)
            title = c.title.replace("|", "/")
            lines.append(f"| {c.status} | {c.id} | {c.area} | {title} | {upstream} |")
        not_pass = [c for c in self.cases if c.status != PASS]
        if not_pass:
            lines += ["", "## Not passed", ""]
            for c in not_pass:
                actual = json.dumps(c.actual, default=str)[:600]
                lines += [f"### {c.status} — {c.id}", "", f"- expected: {c.expected}"]
                lines += [f"- actual: `{actual}`", ""]
        return "\n".join(lines) + "\n"
