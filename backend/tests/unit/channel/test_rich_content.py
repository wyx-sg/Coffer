from coffer.domain.channel.rich_content import (
    ForwardedItem,
    flatten_context,
    flatten_forwarded,
    quote_prefix,
)


def test_flatten_forwarded_block():
    out = flatten_forwarded([ForwardedItem("a@x", "hi"), ForwardedItem("b@x", "[image] u")])
    assert out.splitlines()[0] == "[Forwarded chat record]"
    assert "a@x: hi" in out and "b@x: [image] u" in out


def test_flatten_context_uses_title():
    out = flatten_context([ForwardedItem("a", "x")], title="Recent group messages")
    assert out.splitlines()[0] == "[Recent group messages]"


def test_flatten_empty_is_empty():
    assert flatten_forwarded([]) == "" and flatten_context([], title="T") == ""


def test_quote_prefix():
    assert quote_prefix("a", "t") == "> a: t\n"
