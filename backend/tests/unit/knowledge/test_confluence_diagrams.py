"""draw.io diagrams in a Confluence page: read locally, never fetched (design §5).

``#R`` carries the diagram itself and is decoded here; ``#G``/``#U``/anything
else names a hosted diagram, listed ``external_embed``. Inline ``data-mxgraph``
viewers keep their ``xml``. Every diagram here is synthetic.
"""

from __future__ import annotations

import base64
import json
import urllib.parse
import zlib
from datetime import UTC, datetime

import pytest

from coffer.domain.knowledge.converter import Conversion
from coffer.infrastructure.knowledge.converters.confluence import StorageInput, convert_export
from coffer.infrastructure.knowledge.converters.confluence.diagrams import decode_r

MODEL = '<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/></root></mxGraphModel>'


def _compress(text: str) -> str:
    deflater = zlib.compressobj(9, zlib.DEFLATED, -15)
    raw = deflater.compress(urllib.parse.quote(text, safe="").encode()) + deflater.flush()
    return base64.b64encode(raw).decode()


def _convert(storage: str) -> Conversion:
    inp = StorageInput(title="Diagrams", body=storage, page_id="7", version=2)
    return convert_export(inp, now=datetime(2026, 1, 1, tzinfo=UTC))


def _html(markup: str) -> str:
    return (
        '<ac:structured-macro ac:name="html" ac:schema-version="1"><ac:plain-text-body>'
        f"<![CDATA[{markup}]]></ac:plain-text-body></ac:structured-macro>"
    )


def _drawio_files(result: Conversion) -> dict[str, bytes]:
    return {f.name: f.data for f in result.files if f.name.endswith(".drawio")}


def test_r_fragment_holding_uri_encoded_mxfile_xml_decodes() -> None:
    mxfile = f'<mxfile><diagram name="P" id="a">{_compress(MODEL)}</diagram></mxfile>'
    assert decode_r("R" + urllib.parse.quote(mxfile, safe="")) == mxfile.encode()


def test_r_fragment_holding_compressed_data_inflates() -> None:
    data = decode_r("R" + urllib.parse.quote(_compress(MODEL), safe=""))
    assert data is not None
    assert data.startswith(b"<mxfile>")
    assert MODEL.encode() in data


@pytest.mark.parametrize(
    "fragment", ["R", "Rnot-base64!!", "R" + base64.b64encode(b"junk").decode()]
)
def test_unreadable_r_fragment_is_none(fragment: str) -> None:
    assert decode_r(fragment) is None


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="a Confluence page imports as a readable source with its pictures and diagrams",
)
def test_viewer_link_with_r_data_in_the_body_is_kept_as_a_drawio_file() -> None:
    mxfile = f'<mxfile><diagram name="P" id="a">{_compress(MODEL)}</diagram></mxfile>'
    href = "https://viewer.diagrams.net/?lightbox=1&amp;title=x.drawio#R" + urllib.parse.quote(
        mxfile, safe=""
    )
    result = _convert(f'<p><a href="{href}">x.drawio</a></p>')
    assert _drawio_files(result) == {"diagram-1.drawio": mxfile.encode()}
    assert "[Diagram: diagram-1.drawio](coffer-asset:diagram-1.drawio)" in result.markdown
    assert result.issues == ()


def test_iframe_with_r_data_is_kept() -> None:
    src = "https://viewer.diagrams.net/?nav=1#R" + urllib.parse.quote(MODEL, safe="")
    result = _convert(_html(f'<iframe src="{src}"></iframe>'))
    files = _drawio_files(result)
    assert list(files) == ["diagram-1.drawio"]
    assert files["diagram-1.drawio"].startswith(b"<mxfile>")


@pytest.mark.acceptance(
    spec="knowledge", scenario="what an import could not keep is listed with its reason"
)
@pytest.mark.parametrize(
    ("fragment", "reason"),
    [
        ("G1AbCdEf", "hosted on Google Drive; not fetched"),
        ("Uhttps%3A%2F%2Fexample.com%2Fd.drawio", "hosted at another URL; not fetched"),
        ("", "hosted on diagrams.net; not fetched"),
    ],
)
def test_hosted_diagram_iframe_is_named_and_listed(fragment: str, reason: str) -> None:
    src = "https://viewer.diagrams.net/?highlight=0000ff" + (f"#{fragment}" if fragment else "")
    result = _convert(_html(f'<iframe frameborder="0" src="{src}"></iframe>'))
    assert f"[Hosted diagram]({src})" in result.markdown
    assert [(i.kind, i.reason) for i in result.issues] == [("external_embed", reason)]
    assert result.metadata["import_status"] == "partial"


def test_hosted_diagram_link_in_the_body_stays_a_plain_link() -> None:
    href = "https://app.diagrams.net/#G1AbCdEf"
    result = _convert(f'<p><a href="{href}">edit</a></p>')
    assert result.markdown.strip() == f"[edit]({href})"
    assert result.issues == ()


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="a Confluence page imports as a readable source with its pictures and diagrams",
)
def test_inline_mxgraph_viewer_keeps_its_xml() -> None:
    mxfile = (
        '<mxfile host="app.diagrams.net"><diagram name="P" id="b">' + MODEL + "</diagram></mxfile>"
    )
    config = json.dumps({"highlight": "#0000ff", "xml": mxfile})
    markup = (
        "<!-- draw.io diagram -->\n"
        f"<div class=\"mxgraph\" data-mxgraph='{config}'></div>\n"
        '<script type="text/javascript" src="https://viewer.diagrams.net/js/viewer-static.min.js"></script>'
    )
    result = _convert(_html(markup))
    assert _drawio_files(result) == {"diagram-1.drawio": mxfile.encode()}
    assert "<script" not in result.markdown
    assert result.issues == ()


def test_bare_graph_model_is_wrapped_in_an_mxfile() -> None:
    config = json.dumps({"xml": MODEL})
    result = _convert(_html(f"<div class=\"mxgraph\" data-mxgraph='{config}'></div>"))
    data = _drawio_files(result)["diagram-1.drawio"]
    assert data.startswith(b"<mxfile>") and MODEL.encode() in data


def test_unreadable_mxgraph_is_listed() -> None:
    result = _convert(_html("<div class=\"mxgraph\" data-mxgraph='{not json'></div>"))
    assert [i.kind for i in result.issues] == ["unsupported_macro"]
    assert _drawio_files(result) == {}
