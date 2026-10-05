"""A whole file masked for the Sync page (spec vault-sync "Show a plaintext
finding in its file"): a value a rule reads across lines is masked on each
line it covers, and only the first keeps a public prefix."""

from __future__ import annotations

import random
import string

from coffer.infrastructure.secret.plaintext_mask import mask_text

_RNG = random.Random(11)
_B64 = string.ascii_letters + string.digits + "+/"


def test_a_private_key_block_is_masked_on_every_line_it_covers() -> None:
    body = ["".join(_RNG.choices(_B64, k=64)) for _ in range(4)]
    begin = "-----BEGIN " + "RSA PRIVATE KEY-----"
    end = "-----END " + "RSA PRIVATE KEY-----"
    text = "\n".join(["notes", begin, *body, end, "after"]) + "\n"

    rows = mask_text(text, "knowledge/n.md")
    assert rows[0][0] == "notes" and rows[-1][0] == "after"
    assert len(rows) == 8
    shown = "".join(m for m, _ in rows)
    assert not any(line in shown for line in body)
    covered = [i for i, (_, values) in enumerate(rows) if values]
    assert covered == list(range(1, 7))
    assert {v.rule for _, vs in rows for v in vs} == {"private-key"}
