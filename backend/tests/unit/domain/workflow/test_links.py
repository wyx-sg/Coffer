"""What a mounted link points at, and what is honestly unknown."""

from __future__ import annotations

import pytest

from coffer.domain.workflow.links import classify_link


@pytest.mark.parametrize(
    ("url", "provider"),
    [
        # Atlassian Cloud serves both products from one host; the path says
        # which, and that is the whole reason the path is looked at at all.
        ("https://mycorp.atlassian.net/wiki/spaces/ENG/pages/123/TD", "confluence"),
        ("https://mycorp.atlassian.net/browse/COF-1", "jira"),
        ("https://mycorp.atlassian.net/jira/software/projects/COF/boards/1", "jira"),
        # Google puts several products on one host, told apart the same way.
        ("https://docs.google.com/document/d/abc/edit", "google_docs"),
        ("https://docs.google.com/spreadsheets/d/abc/edit#gid=0", "google_sheets"),
        ("https://docs.google.com/presentation/d/abc/edit", "google_slides"),
        ("https://drive.google.com/file/d/abc/view", "google_drive"),
        # One host, one product.
        ("https://github.com/anthropics/coffer/pull/398", "github"),
        ("https://gitlab.com/shopee/core-server/account/-/merge_requests/7", "gitlab"),
        ("https://www.figma.com/file/abc/Design", "figma"),
        ("https://acme.notion.so/Plan-123", "notion"),
        ("https://acme.slack.com/archives/C123/p1700000000", "slack"),
        # Self-hosted, named after the product it runs.
        ("https://confluence.example.com/display/ENG/TD", "confluence"),
        ("https://jira.internal/browse/COF-1", "jira"),
        ("https://wiki.corp.example/display/ENG/TD", "confluence"),
    ],
)
def test_a_link_is_named_when_it_can_be_recognised(url: str, provider: str) -> None:
    assert classify_link(url) == provider


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/some/page",
        "https://news.ycombinator.com/item?id=1",
        "http://localhost:8080/docs",
    ],
)
def test_an_ordinary_page_is_not_given_a_label_it_has_not_earned(url: str) -> None:
    # `None` is the honest answer and lets a node fall back to fetching. A
    # `web` label would be a guess wearing a name, and a node that believed it
    # had been told something would reach for the wrong tool.
    assert classify_link(url) is None


@pytest.mark.parametrize("url", ["", "   ", "not a url", "mailto:someone@example.com", "://x"])
def test_something_that_is_not_an_addressable_url_is_unknown_rather_than_an_error(
    url: str,
) -> None:
    # A link input is whatever the developer typed; classifying it must never
    # be the thing that refuses their input.
    assert classify_link(url) is None


def test_recognition_is_case_insensitive_on_the_host() -> None:
    assert classify_link("https://MyCorp.Atlassian.NET/browse/COF-1") == "jira"


def test_a_subdomain_of_a_known_host_counts_but_a_lookalike_does_not() -> None:
    assert classify_link("https://gist.github.com/someone/abc") == "github"
    # `github.com.evil.test` is not GitHub, and suffix matching that ignored
    # the dot boundary would say it was.
    assert classify_link("https://github.com.evil.test/anthropics/coffer") is None
