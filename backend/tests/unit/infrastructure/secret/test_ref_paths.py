"""A credential ref is a name, and its file name is that name made safe
(ADR storage-is-five-classes-by-nature: "the file name being the opaque ref")."""

from __future__ import annotations

import pytest

from coffer.infrastructure.secret.ref_paths import (
    is_local_ref,
    ref_to_relpath,
    relpath_to_ref,
)


@pytest.mark.parametrize(
    ("ref", "relpath"),
    [
        ("github-token", "github-token.enc"),
        ("channel/seatalk/app-secret", "channel/seatalk/app-secret.enc"),
        ("secret/GH_TOKEN.v2", "secret/GH_TOKEN.v2.enc"),
        ("a b/c", "a%20b/c.enc"),
        ("100%", "100%25.enc"),
        ("x/.git", "x/%2Egit.enc"),
        (".hidden", "%2Ehidden.enc"),
        ("a.b", "a.b.enc"),
        ("ключ", "%D0%BA%D0%BB%D1%8E%D1%87.enc"),
        ("back\\slash:colon", "back%5Cslash%3Acolon.enc"),
    ],
)
def test_a_ref_maps_to_its_path_and_back(ref: str, relpath: str) -> None:
    assert ref_to_relpath(ref) == relpath
    assert relpath_to_ref(relpath) == ref


@pytest.mark.parametrize("ref", ["", "/", "a//b", "../x", "a/..", "a/./b", "/abs", "trailing/"])
def test_a_ref_with_an_empty_or_dot_segment_is_refused(ref: str) -> None:
    with pytest.raises(ValueError):
        ref_to_relpath(ref)


@pytest.mark.parametrize(
    "relpath",
    [
        "a.txt",  # another suffix
        ".a.enc.123.tmp",  # an atomic write's temp file
        ".hidden.enc",  # a leading dot is always escaped when Coffer writes it
        "a%2fb.enc",  # a non-canonical escape: one ref has one file
        "a%2Fb.enc",  # an escaped separator is not a segment boundary
        "%FF.enc",  # not UTF-8
        "a b.enc",  # a raw character Coffer would have escaped
    ],
)
def test_a_file_coffer_would_not_have_written_is_not_a_ref(relpath: str) -> None:
    assert relpath_to_ref(relpath) is None


def test_proxy_tokens_are_the_machine_local_family() -> None:
    assert is_local_ref("proxy-token/agent-1")
    assert not is_local_ref("proxy/agent-1")
    assert not is_local_ref("secret/proxy-token")
