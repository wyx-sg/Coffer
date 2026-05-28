"""SSRF guard host predicate."""

from __future__ import annotations

import pytest

from coffer.infrastructure.skill.ssrf_guard import check_url, is_blocked_host


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "::1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",  # AWS metadata
        "[fe80::1]",
        "",
        "   ",
    ],
)
def test_blocks_private_loopback_linklocal(host):
    assert is_blocked_host(host) is True


def test_blocks_unresolvable():
    assert is_blocked_host("definitely-not-a-real-host-coffer-test.invalid") is True


def test_check_url_rejects_loopback():
    with pytest.raises(ValueError, match="SSRF"):
        check_url("http://127.0.0.1/repo.git")


def test_check_url_rejects_non_http_scheme():
    with pytest.raises(ValueError, match="unsupported scheme"):
        check_url("ssh://git@example.com/repo.git")


def test_check_url_rejects_empty_host():
    with pytest.raises(ValueError, match="no host"):
        check_url("http:///path")


# TEST21-002: positive cases — `is_blocked_host` must NOT block obviously
# public hosts. Without an allow-path assertion the guard could regress to
# rejecting everything and still pass the negative tests above.
def test_allows_public_dns_host():
    """A public DNS name resolves to public IPs and is not blocked."""
    # `example.com` is reserved for documentation and always resolves to
    # a public IPv4/IPv6 address (RFC 2606). No risk of a sandbox running
    # this test resolving it to a private range.
    assert is_blocked_host("example.com") is False


def test_check_url_rejects_private_via_check_url():
    """check_url must reject an RFC1918 literal even though it is reachable."""
    with pytest.raises(ValueError, match="SSRF"):
        check_url("http://10.0.0.1/")
