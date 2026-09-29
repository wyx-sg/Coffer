"""The archive reader refuses before it writes (spec skill-manager "Add skills
from an archive", "unsafe archive entries are rejected before anything is
written").

Driven with a small cap so the over-the-cap cases stay fast; the 50 MB cap
itself is the service's default and is exercised through the routes.
"""

from __future__ import annotations

import io
import pathlib
import zipfile

import pytest

from coffer.domain.errors import SkillSourceRejected
from coffer.infrastructure.skill.archive_reader import extract_archive, save_upload
from tests.support.skill_sources import skill_md, symlink_zip, zip_bytes

CAP = 4096


def _archive(tmp_path: pathlib.Path, data: bytes) -> pathlib.Path:
    path = tmp_path / "upload.zip"
    path.write_bytes(data)
    return path


def _refused(tmp_path: pathlib.Path, data: bytes) -> SkillSourceRejected:
    dest = tmp_path / "tree"
    with pytest.raises(SkillSourceRejected) as info:
        extract_archive(_archive(tmp_path, data), dest, cap_bytes=CAP)
    return info.value


def _files(root: pathlib.Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def test_a_clean_archive_is_extracted_without_archiver_junk(tmp_path: pathlib.Path) -> None:
    data = zip_bytes(
        {
            "review/SKILL.md": skill_md("review"),
            "review/scripts/run.sh": "echo hi\n",
            "__MACOSX/review/._SKILL.md": "junk",
            "review/.DS_Store": "junk",
        }
    )
    dest = tmp_path / "tree"
    extract_archive(_archive(tmp_path, data), dest, cap_bytes=CAP)
    assert _files(dest) == ["review/SKILL.md", "review/scripts/run.sh"]


@pytest.mark.parametrize(
    ("entry", "problem"),
    [
        ("../evil.sh", "parent_segment"),
        ("review/../../evil.sh", "parent_segment"),
        ("/etc/evil.sh", "absolute_path"),
        ("\\evil.sh", "absolute_path"),
        ("C:evil.sh", "absolute_path"),
    ],
)
def test_an_entry_that_would_land_outside_is_refused_by_name(
    tmp_path: pathlib.Path, entry: str, problem: str
) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("review/SKILL.md", skill_md("review"))
        # writestr normalises some names; ZipInfo keeps the hostile one as is.
        zf.writestr(zipfile.ZipInfo(entry), "x")
    err = _refused(tmp_path, buf.getvalue())
    assert err.reason == "archive_unsafe_entries"
    assert err.error_details["offenders"] == [{"entry": entry, "problem": problem}]
    assert entry in str(err)
    assert not (tmp_path / "tree").exists(), "nothing is extracted before the check"
    assert not (tmp_path.parent / "evil.sh").exists()


def test_a_symlink_entry_is_refused_by_name(tmp_path: pathlib.Path) -> None:
    data = symlink_zip("review/link", "/etc/passwd", {"review/SKILL.md": skill_md("review")})
    err = _refused(tmp_path, data)
    assert err.error_details["offenders"] == [{"entry": "review/link", "problem": "symlink"}]
    assert not (tmp_path / "tree").exists()


def test_every_offender_is_named_at_once(tmp_path: pathlib.Path) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(zipfile.ZipInfo("../a"), "x")
        zf.writestr(zipfile.ZipInfo("/b"), "x")
    err = _refused(tmp_path, buf.getvalue())
    assert [o["entry"] for o in err.error_details["offenders"]] == ["../a", "/b"]  # type: ignore[union-attr]


def test_declared_sizes_past_the_cap_are_refused_before_extracting(
    tmp_path: pathlib.Path,
) -> None:
    data = zip_bytes({"review/SKILL.md": skill_md("review"), "review/big.txt": "x" * (CAP + 1)})
    err = _refused(tmp_path, data)
    assert err.reason == "size_limit_exceeded"
    assert err.error_details["limit_bytes"] == CAP
    assert err.error_details["offenders"] == [{"entry": "review/big.txt", "problem": "size_limit"}]
    assert "review/big.txt" in str(err)
    assert not (tmp_path / "tree").exists()


def _lying_zip(real: bytes, declared: int) -> bytes:
    """A stored entry whose central-directory size claims ``declared`` bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("review/SKILL.md", skill_md("review"))
        zf.writestr("review/bomb.bin", real)
    raw = bytearray(buf.getvalue())
    # Patch the uncompressed size in the central directory record of bomb.bin.
    cd = raw.rfind(b"PK\x01\x02", 0, raw.rfind(b"review/bomb.bin"))
    assert cd != -1
    raw[cd + 24 : cd + 28] = declared.to_bytes(4, "little")
    return bytes(raw)


def test_a_lying_size_header_is_refused_naming_the_entry(tmp_path: pathlib.Path) -> None:
    """The header claims 10 bytes, the entry holds twice the cap: the total the
    archive declares passes the pre-check, and reading the entry is what
    refuses it (the decompressor stops at the declared size and the CRC fails)
    — a refusal naming the entry, never a server error."""
    data = _lying_zip(b"y" * (CAP * 2), declared=10)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        assert sum(i.file_size for i in zf.infolist()) < CAP, "the header lies"
    err = _refused(tmp_path, data)
    assert err.reason == "archive_unreadable"
    assert err.error_details["offenders"] == [{"entry": "review/bomb.bin", "problem": "corrupt"}]
    bomb = tmp_path / "tree" / "review" / "bomb.bin"
    assert not bomb.exists() or bomb.stat().st_size <= 10


def test_the_cap_is_judged_on_the_whole_archive_not_each_entry(tmp_path: pathlib.Path) -> None:
    """Every entry is under the cap on its own; together they are not."""
    half = CAP // 2 + 1
    data = zip_bytes({"review/SKILL.md": skill_md("review"), "review/a": "a" * half})
    extract_archive(_archive(tmp_path, data), tmp_path / "ok", cap_bytes=CAP)
    two = zip_bytes({"review/a": "a" * half, "review/b": "b" * half})
    err = _refused(tmp_path, two)
    assert err.reason == "size_limit_exceeded"
    assert err.error_details["offenders"] == [{"entry": "review/b", "problem": "size_limit"}]


def test_a_file_that_is_not_a_zip_is_refused(tmp_path: pathlib.Path) -> None:
    err = _refused(tmp_path, b"not a zip at all")
    assert err.reason == "archive_unreadable"


def test_an_upload_past_the_cap_is_refused_while_saved(tmp_path: pathlib.Path) -> None:
    dest = tmp_path / "upload.zip"
    with pytest.raises(SkillSourceRejected) as info:
        save_upload(io.BytesIO(b"z" * (CAP + 1)), dest, cap_bytes=CAP)
    assert info.value.reason == "archive_too_large"
    assert save_upload(io.BytesIO(b"z" * CAP), dest, cap_bytes=CAP) == CAP
    assert dest.read_bytes() == b"z" * CAP
