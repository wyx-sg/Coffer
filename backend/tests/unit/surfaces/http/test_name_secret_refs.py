"""An audit row naming a secret also carries the label the secret has right now."""

from __future__ import annotations

import pytest

from coffer.domain.secrets import SecretNote
from coffer.surfaces.http import secret_notes_wiring
from coffer.surfaces.http.secret_notes_wiring import name_secret_refs

REF = "secret/fe55638667a74ca18a73e78cf67f5fe5"


class _Notes:
    def __init__(self, notes: dict[str, SecretNote]) -> None:
        self._notes = notes

    def get(self, ref: str) -> SecretNote | None:
        return self._notes.get(ref)


@pytest.fixture
def notes(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _Notes({REF: SecretNote(label="Git token"), "secret/aa": SecretNote(description="x")})
    monkeypatch.setattr(secret_notes_wiring, "_notes", fake)


def test_a_labelled_secret_is_named(notes: None) -> None:
    assert name_secret_refs({"ref": REF, "slot": "token"}) == {
        "ref": REF,
        "slot": "token",
        "ref_label": "Git token",
    }


def test_an_unlabelled_secret_or_a_row_without_a_ref_is_left_alone(notes: None) -> None:
    assert name_secret_refs({"ref": "secret/aa"}) == {"ref": "secret/aa"}
    assert name_secret_refs({"op": "disable_protection"}) == {"op": "disable_protection"}


def test_a_label_the_caller_filed_is_kept(notes: None) -> None:
    row = {"ref": REF, "ref_label": "Before"}
    assert name_secret_refs(row) == row


def test_a_bare_app_without_notes_changes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(secret_notes_wiring, "_notes", None)
    assert name_secret_refs({"ref": REF}) == {"ref": REF}
