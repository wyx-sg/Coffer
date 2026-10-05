"""A rule runs only around its keywords in a long text, and a long text scans fast
(spec secret "Detect plaintext secrets with the bundled rules")."""

from __future__ import annotations

import base64
import random
import time

from coffer.infrastructure.secret import detector
from tests.support.gitleaks_hand_samples import rand

GH = "ghp_" + rand("gh", 36)
PEM = (
    "-----BEGIN "
    + "PRIVATE KEY-----\n"
    + "\n".join(rand("pem", 64) for _ in range(12))
    + "\n-----END "
    + "PRIVATE KEY-----"
)


def _shifted(text: str, offset: int) -> list[tuple[str, int, int]]:
    return [(d.rule, d.start + offset, d.end + offset) for d in detector.detect(text)]


def test_a_value_deep_in_a_long_text_is_found_where_a_short_text_finds_it() -> None:
    short = f"token: {GH}\n"
    filler = "lorem ipsum dolor sit amet\n" * 2000
    assert len(filler) > detector.WHOLE_TEXT
    long_text = filler + short + filler
    assert [(r, s, e) for r, s, e in _shifted(short, len(filler))] == [
        (d.rule, d.start, d.end) for d in detector.detect(long_text)
    ]
    assert _shifted(short, 0)[0][0] == "github-pat"


def test_several_values_in_one_long_text_are_each_found_once() -> None:
    filler = "x" * (detector.WINDOW_AFTER * 3) + "\n"
    text = f"a {GH}\n{filler}b {GH}\n{filler}"
    found = detector.detect(text)
    assert [d.rule for d in found] == ["github-pat", "github-pat"]
    assert len({d.start for d in found}) == 2


def test_a_private_key_longer_than_the_ordinary_window_is_found_whole() -> None:
    filler = "lorem ipsum dolor sit amet\n" * 1000
    text = filler + PEM + "\n" + filler
    found = detector.detect(text)
    assert [d.rule for d in found] == ["private-key"]
    start, end = found[0].start, found[0].end
    assert text[start:end].count("\n") >= 12
    assert "lorem" not in text[start:end]


def test_a_text_with_no_keyword_is_not_run_through_a_rule() -> None:
    assert detector.detect("nothing to see here, just words " * 5000) == []


def test_a_megabyte_of_base64_on_one_line_scans_in_seconds() -> None:
    blob = base64.b64encode(random.Random("blob").randbytes(768 * 1024)).decode()
    assert 1_000_000 <= len(blob) <= 1_100_000 and "\n" not in blob
    for text in (blob, f"note = {blob}\n"):
        started = time.perf_counter()
        detector.detect(text)
        assert time.perf_counter() - started < 3.0
