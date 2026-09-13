"""CSV/TSV → Markdown table converter (stdlib ``csv`` only)."""

from __future__ import annotations

import csv
import io

from coffer.domain.knowledge.converter import Conversion, derive_title


class CsvConverter:
    """Renders a CSV/TSV file as a GitHub-flavoured Markdown table."""

    def can_handle(self, fmt: str) -> bool:
        return fmt.lower().lstrip(".") in {"csv", "tsv"}

    async def convert(self, data: bytes, filename: str) -> Conversion:
        delimiter = "\t" if filename.lower().endswith(".tsv") else ","
        text = data.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        rows = [row for row in reader if any(cell.strip() for cell in row)]
        if not rows:
            return Conversion(markdown="", title=derive_title("", filename), converter="csv")
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        header, body = rows[0], rows[1:]
        lines = [
            "| " + " | ".join(_escape(c) for c in header) + " |",
            "| " + " | ".join(["---"] * width) + " |",
        ]
        lines += ["| " + " | ".join(_escape(c) for c in row) + " |" for row in body]
        markdown = "\n".join(lines) + "\n"
        return Conversion(
            markdown=markdown, title=derive_title(markdown, filename), converter="csv"
        )


def _escape(cell: str) -> str:
    return cell.replace("|", "\\|").replace("\n", " ").strip()
