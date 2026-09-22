"""What a run read, written down so it survives the run (FR-043)."""

from __future__ import annotations

from coffer.application.workflow.promotion import references_markdown
from coffer.domain.workflow.run import RunInput, RunInputKind


def test_a_run_that_read_nothing_external_gets_no_file() -> None:
    """An empty `references.md` in a collection is a question every later
    reader has to open to answer."""
    uploads = (
        RunInput(kind=RunInputKind.FILE, ref="prd.pdf"),
        RunInput(kind=RunInputKind.NOTE, ref="ops.md"),
    )
    assert references_markdown("Ship it", uploads) is None
    assert references_markdown("Ship it", ()) is None


def test_links_collections_and_repositories_are_recorded_as_addresses() -> None:
    """They are not the run's bytes to copy: a page belongs to whoever
    published it, a collection is already in this vault, and a checkout went
    with the run. What is kept is that this delivery read them."""
    text = references_markdown(
        "Ship the retry fix",
        (
            RunInput(
                kind=RunInputKind.LINK,
                ref="https://mycorp.atlassian.net/wiki/spaces/ENG/pages/1/TD",
                label="技术方案",
            ),
            RunInput(kind=RunInputKind.KNOWLEDGE, ref="account-service"),
            RunInput(kind=RunInputKind.REPO, ref="/src/checkout", label="the service"),
            # Copied bodily, so naming it here would say the same thing twice
            # about a file sitting in the same directory.
            RunInput(kind=RunInputKind.FILE, ref="prd.pdf"),
        ),
    )

    assert text is not None
    assert "# References — Ship the retry fix" in text
    # The provider is named, so a reader knows what kind of page it was.
    assert "(confluence) — 技术方案" in text
    assert "- knowledge collection `account-service`" in text
    assert "- repository `/src/checkout` — the service" in text
    assert "prd.pdf" not in text
