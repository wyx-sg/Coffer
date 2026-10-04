"""Header forwarding rules and wire-shaped errors."""

from __future__ import annotations

import json

from coffer.domain.model_proxy.state import ProxyMember, UpstreamAuth
from coffer.domain.usage.records import Wire
from coffer.infrastructure.model_proxy import wire as w


def _member(
    auth: UpstreamAuth, key: str | None = "sk-real", root: str = "https://api.example"
) -> ProxyMember:
    return ProxyMember(
        connection_uid="c", connection_name="C", upstream_root=root, auth=auth, key=key
    )


_CLIENT = [
    (b"host", b"127.0.0.1:38471"),
    (b"authorization", b"Bearer local-token"),
    (b"x-api-key", b"local-token"),
    (b"cookie", b"a=b"),
    (b"accept-encoding", b"gzip, br"),
    (b"content-length", b"10"),
    (b"connection", b"keep-alive, x-drop-me"),
    (b"x-drop-me", b"1"),
    (b"anthropic-beta", b"future-feature-2099"),
    (b"anthropic-beta", b"second-value"),
    (b"x-coffer-proxy-control", b"secret"),
    (b"x-custom", b"kept"),
]


def test_forwarded_headers_drop_credentials_and_hop_by_hop_but_keep_the_rest() -> None:
    out = w.upstream_request_headers(_CLIENT, _member(UpstreamAuth.ANTHROPIC))
    names = [k for k, _ in out]
    for dropped in (
        b"host",
        b"cookie",
        b"content-length",
        b"connection",
        b"x-drop-me",
        b"x-coffer-proxy-control",
    ):
        assert dropped not in names
    assert [v for k, v in out if k == b"anthropic-beta"] == [
        b"future-feature-2099",
        b"second-value",
    ]
    assert (b"x-custom", b"kept") in out
    assert (b"accept-encoding", b"identity") in out
    assert [v for k, v in out if k == b"x-api-key"] == [b"sk-real"]
    assert [v for k, v in out if k == b"authorization"] == [b"Bearer sk-real"]


def test_bearer_and_keyless_members() -> None:
    bearer = w.upstream_request_headers(_CLIENT, _member(UpstreamAuth.BEARER))
    assert [v for k, v in bearer if k == b"authorization"] == [b"Bearer sk-real"]
    assert b"x-api-key" not in [k for k, _ in bearer]
    none = w.upstream_request_headers(_CLIENT, _member(UpstreamAuth.NONE, key=None))
    assert not {b"authorization", b"x-api-key"} & {k for k, _ in none}


def test_response_headers_drop_framing_only() -> None:
    out = w.client_response_headers(
        [
            (b"content-type", b"text/event-stream"),
            (b"content-length", b"5"),
            (b"transfer-encoding", b"chunked"),
            (b"retry-after", b"3"),
            (b"request-id", b"req_1"),
        ]
    )
    assert out == [
        (b"content-type", b"text/event-stream"),
        (b"retry-after", b"3"),
        (b"request-id", b"req_1"),
    ]


def test_upstream_url_and_loopback_detection() -> None:
    member = _member(UpstreamAuth.BEARER, root="http://127.0.0.1:11434/")
    assert (
        w.upstream_url(member, "/v1/responses", b"a=1") == "http://127.0.0.1:11434/v1/responses?a=1"
    )
    assert w.is_loopback_member(member)
    assert not w.is_loopback_member(_member(UpstreamAuth.BEARER))


def test_request_meta_reads_a_copy_only() -> None:
    assert w.request_meta(b'{"model": "m", "stream": true}') == ("m", True)
    assert w.request_meta(b"not json") == (None, False)
    assert w.request_meta(b'["x"]') == (None, False)


def test_error_bodies_follow_each_wire() -> None:
    assert json.loads(w.error_body(Wire.ANTHROPIC, "nope")) == {
        "type": "error",
        "error": {"type": "api_error", "message": "nope"},
    }
    assert json.loads(w.error_body(Wire.OPENAI, "nope")) == {
        "error": {"message": "nope", "type": "api_error"}
    }
