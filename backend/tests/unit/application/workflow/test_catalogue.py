"""CATALOG.md is generated from the directory and never hand-maintained (FR-031)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from coffer.application.workflow.catalogue import regenerate_catalogue, render_catalogue


@dataclass(frozen=True)
class FakeEntry:
    name: str
    node_key: str
    attempt: int
    path: str
    size: int
    modified_at: datetime


class FakeStore:
    """The slice of ``ArtifactStorePort`` the catalogue touches."""

    def __init__(self, entries: Sequence[FakeEntry]) -> None:
        self.entries = list(entries)
        self.written: list[str] = []

    def run_dir(self, run_id: str) -> str:
        return f"/runs/{run_id}"

    def ensure_run_dirs(self, run_id: str) -> None: ...

    def list_artifacts(self, run_id: str) -> Sequence[FakeEntry]:
        return list(self.entries)

    def write_catalogue(self, run_id: str, markdown: str) -> None:
        self.written.append(markdown)

    def read_catalogue(self, run_id: str) -> str:
        return self.written[-1] if self.written else ""

    def collect_run_files(
        self, run_id: str, destination: str, *, references: str | None = None
    ) -> int:
        return 0

    def delete_run_dir(self, run_id: str) -> None: ...


def entry(name: str, node: str, attempt: int, *, size: int = 12) -> FakeEntry:
    return FakeEntry(
        name=name,
        node_key=node,
        attempt=attempt,
        path=f"{node}/{attempt}/{name}",
        size=size,
        modified_at=datetime(2026, 9, 17, 8, 30, 0, tzinfo=UTC),
    )


def test_empty_run_says_so_rather_than_rendering_an_empty_table() -> None:
    text = render_catalogue([])

    assert "No artifacts yet." in text
    assert "| ---" not in text


def test_every_row_names_the_node_and_the_attempt_that_produced_it() -> None:
    text = render_catalogue([entry("td.md", "draft_td", 2, size=2048)])

    row = next(line for line in text.splitlines() if "td.md" in line and line.startswith("|"))
    assert "`draft_td`" in row
    assert "| 2 |" in row
    assert "`artifacts/draft_td/2/td.md`" in row
    assert "2.0 KB" in row
    assert "2026-09-17 08:30:00" in row


def test_regenerating_twice_over_the_same_directory_is_byte_identical() -> None:
    store = FakeStore([entry("td.md", "draft_td", 1), entry("report.md", "test", 1)])

    first = regenerate_catalogue(store, "run-1")
    second = regenerate_catalogue(store, "run-1")

    assert first == second
    assert store.written == [first, second]


def test_rows_are_ordered_by_node_then_attempt_then_name_whatever_the_store_says() -> None:
    forwards = render_catalogue(
        [
            entry("a.md", "alpha", 1),
            entry("b.md", "alpha", 2),
            entry("c.md", "beta", 1),
        ]
    )
    backwards = render_catalogue(
        [
            entry("c.md", "beta", 1),
            entry("b.md", "alpha", 2),
            entry("a.md", "alpha", 1),
        ]
    )

    assert forwards == backwards
    body = [line for line in forwards.splitlines() if line.startswith("| `")]
    assert [line.split("`")[1] for line in body] == ["a.md", "b.md", "c.md"]


def test_an_adhoc_node_keeps_its_colon_in_the_catalogue() -> None:
    text = render_catalogue([entry("notes.md", "adhoc:hotfix", 1)])

    assert "`adhoc:hotfix`" in text


def test_a_pipe_on_disk_cannot_break_the_table() -> None:
    text = render_catalogue([entry("we|ird.md", "node", 1)])

    row = next(line for line in text.splitlines() if "ird.md" in line)
    # Six cells, so seven delimiters — and none of them came from the filename.
    assert row.replace("\\|", "").count("|") == 7
    assert "we\\|ird.md" in row


def test_the_catalogue_tells_its_reader_not_to_edit_it() -> None:
    text = render_catalogue([entry("td.md", "draft_td", 1)])

    assert "Edits are overwritten" in text
