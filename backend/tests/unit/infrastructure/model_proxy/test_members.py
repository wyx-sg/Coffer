"""Member eligibility, health and session affinity."""

from __future__ import annotations

from coffer.domain.model_proxy.state import ProxyMember, ProxyRoute, UpstreamAuth
from coffer.domain.usage.records import Wire
from coffer.infrastructure.model_proxy.members import MemberBook, parse_retry_after


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _m(
    uid: str, models: list[str] | None = None, *, local: bool = False, key: str = "k"
) -> ProxyMember:
    return ProxyMember(
        connection_uid=uid,
        connection_name=uid.upper(),
        upstream_root=f"https://{uid}.example",
        auth=UpstreamAuth.ANTHROPIC,
        key=key,
        models=models or [],
        local=local,
    )


def _route(*members: ProxyMember) -> ProxyRoute:
    return ProxyRoute(agent_uid="agent", wire=Wire.ANTHROPIC, members=list(members))


def _uids(members: list[ProxyMember]) -> list[str]:
    return [m.connection_uid for m in members]


def test_fallback_needs_the_requested_model_listed() -> None:
    book = MemberBook()
    route = _route(_m("a"), _m("b", ["other"]), _m("c", ["m1"]), _m("d"))
    assert _uids(book.candidates(route, "m1", None)) == ["a", "c"]
    assert _uids(book.candidates(route, None, None)) == ["a"]


def test_local_members_never_take_part_in_failover() -> None:
    book = MemberBook()
    assert _uids(book.candidates(_route(_m("a"), _m("l", ["m1"], local=True)), "m1", None)) == ["a"]
    local_primary = _route(_m("l", local=True), _m("b", ["m1"]))
    assert _uids(book.candidates(local_primary, "m1", None)) == ["l"]


def test_rate_limit_cools_for_retry_after_then_returns() -> None:
    clock = _Clock()
    book = MemberBook(clock=clock)
    a, b = _m("a"), _m("b", ["m1"])
    book.rate_limited(a, 60)
    assert _uids(book.candidates(_route(a, b), "m1", None)) == ["b"]
    clock.now += 61
    assert _uids(book.candidates(_route(a, b), "m1", None)) == ["a", "b"]


def test_transient_failure_rests_briefly() -> None:
    clock = _Clock()
    book = MemberBook(clock=clock)
    a, _b = _m("a"), _m("b", ["m1"])
    book.rest(a)
    assert not book.available(a)
    clock.now += 31
    assert book.available(a)


def test_auth_failure_disables_until_the_member_changes() -> None:
    clock = _Clock()
    book = MemberBook(clock=clock)
    a, b = _m("a"), _m("b", ["m1"])
    book.auth_failed(a)
    clock.now += 10_000
    assert book.disabled(a) and _uids(book.candidates(_route(a, b), "m1", None)) == ["b"]
    book.reconcile([a, b])  # same key: still disabled
    assert book.disabled(a)
    fixed = _m("a", key="new-key")
    book.reconcile([fixed, b])
    assert not book.disabled(fixed) and book.available(fixed)


def test_every_member_resting_still_tries_the_primary() -> None:
    book = MemberBook()
    a, b = _m("a"), _m("b", ["m1"])
    book.rest(a)
    book.auth_failed(b)
    assert _uids(book.candidates(_route(a, b), "m1", None)) == ["a"]


def test_session_sticks_to_its_member_until_that_member_fails() -> None:
    book = MemberBook()
    a, b = _m("a", ["m1"]), _m("b", ["m1"])
    route = _route(a, b)
    book.served(b, "agent", "s1")
    assert _uids(book.candidates(route, "m1", "s1")) == ["b", "a"]
    assert _uids(book.candidates(route, "m1", "s2")) == ["a", "b"]
    book.rest(b)
    assert _uids(book.candidates(route, "m1", "s1")) == ["a"]


def test_each_member_is_planned_once() -> None:
    book = MemberBook()
    route = _route(_m("a"), _m("a", ["m1"]), _m("b", ["m1"]), _m("b", ["m1"]))
    assert _uids(book.candidates(route, "m1", None)) == ["a", "b"]


def test_retry_after_parses_seconds_and_http_dates() -> None:
    assert parse_retry_after("12") == 12.0
    assert parse_retry_after(None) is None and parse_retry_after("soon") is None
    assert parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT", now=1445412470.0) == 10.0
