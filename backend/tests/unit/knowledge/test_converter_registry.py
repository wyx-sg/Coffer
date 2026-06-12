"""Unit tests for converter dispatch + cleaning. Pure (no engine libs needed)."""

import pytest

from coffer.domain.errors import IngestRejected
from coffer.infrastructure.knowledge.converters import default_registry
from coffer.infrastructure.knowledge.converters.csv_converter import CsvConverter
from coffer.infrastructure.knowledge.converters.passthrough_converter import (
    PassthroughConverter,
)


@pytest.mark.asyncio
async def test_passthrough_handles_markdown_and_code() -> None:
    reg = default_registry()
    md, meta = await reg.convert(b"# Title\n\nbody", "md")
    assert "# Title" in md
    assert meta["conversion_engine"] == "passthrough"
    code, _ = await reg.convert(b"def f():\n    return 1\n", "py")
    assert "def f" in code


@pytest.mark.asyncio
async def test_csv_renders_markdown_table() -> None:
    out, meta = await CsvConverter().convert(b"a,b\n1,2\n3,4\n", "csv")
    assert "| a | b |" in out
    assert "| --- | --- |" in out
    assert "| 1 | 2 |" in out
    assert meta["conversion_engine"] == "csv"


@pytest.mark.asyncio
async def test_registry_routes_csv_before_markitdown() -> None:
    reg = default_registry()
    out, meta = await reg.convert(b"x,y\n1,2\n", "csv")
    assert meta["conversion_engine"] == "csv"
    assert "| x | y |" in out


@pytest.mark.asyncio
async def test_unsupported_format_rejected() -> None:
    reg = default_registry()
    with pytest.raises(IngestRejected) as exc:
        await reg.convert(b"\x00\x01", "xyz")
    assert exc.value.reason == "unsupported_type"


@pytest.mark.asyncio
async def test_empty_conversion_rejected() -> None:
    reg = default_registry()
    with pytest.raises(IngestRejected) as exc:
        await reg.convert(b"   \n\n  ", "txt")
    assert exc.value.reason == "empty"


def test_passthrough_can_handle_strips_dot() -> None:
    assert PassthroughConverter().can_handle(".md") is True
    assert PassthroughConverter().can_handle("MD") is True
    assert PassthroughConverter().can_handle("pdf") is False


def test_registry_supports() -> None:
    reg = default_registry()
    assert reg.supports("csv") is True
    assert reg.supports("pdf") is True  # markitdown claims it (lazy)
    assert reg.supports("zzz") is False
