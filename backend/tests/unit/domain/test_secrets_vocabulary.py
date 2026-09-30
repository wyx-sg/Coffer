"""Standalone secret names, their URIs and the output mask (spec secret
"Resolve standalone secrets into one child with coffer run")."""

from __future__ import annotations

import pytest

from coffer.domain.mcp.secret_target import secret_target
from coffer.domain.mcp.server_config import HttpTransport, StdioTransport
from coffer.domain.secret_masking import StreamMasker
from coffer.domain.secrets import (
    cited_secret_names,
    default_env_var,
    is_standalone_ref,
    is_valid_secret_name,
    parse_secret_uri,
)


def test_names_uris_and_default_variables() -> None:
    assert is_valid_secret_name("db-password.prod")
    assert not is_valid_secret_name("a/b") and not is_valid_secret_name("..")
    assert not is_valid_secret_name("x" * 65)
    assert parse_secret_uri(" coffer://secret/db-password ") == "db-password"
    assert parse_secret_uri("coffer://secret/a/b") is None
    assert cited_secret_names("use coffer://secret/a and coffer://secret/b.c") == {"a", "b.c"}
    assert default_env_var("db-password.prod") == "DB_PASSWORD_PROD"
    assert is_standalone_ref("secret/x") and not is_standalone_ref("mcp_server/x/TOKEN")


def test_a_value_split_across_two_reads_is_still_masked() -> None:
    masker = StreamMasker(["s3cret-value-123"])
    out = masker.feed(b"token=s3cret-v") + masker.feed(b"alue-123 done\n") + masker.flush()
    assert out == b"token=*** done\n"


def test_short_values_are_not_masked_and_output_passes_through() -> None:
    masker = StreamMasker(["abc"])
    assert not masker.active
    assert masker.feed(b"abc") == b"abc"


@pytest.mark.parametrize("chunk", [1, 2, 5, 100])
def test_masking_holds_for_any_chunk_size(chunk: int) -> None:
    text = b"a=longsecretvalue b=longsecretvalue\n"
    masker = StreamMasker(["longsecretvalue"])
    out = b"".join(masker.feed(text[i : i + chunk]) for i in range(0, len(text), chunk))
    assert out + masker.flush() == b"a=*** b=***\n"


def test_the_target_of_a_stdio_server_includes_what_can_redirect_it() -> None:
    stdio = StdioTransport(
        command="npx", args=["-y", "server"], env={"NODE_OPTIONS": "--x"}, cwd="/w"
    )
    assert secret_target(stdio) == "stdio npx -y server in /w with NODE_OPTIONS=--x"
    assert secret_target(HttpTransport(url="https://mcp.example.com/")) == (
        "http https://mcp.example.com/"
    )
