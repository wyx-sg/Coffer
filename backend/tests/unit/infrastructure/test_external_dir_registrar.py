"""Unit tests for YamlExternalDirRegistrar (spec 005, EXTERNAL_DIR delivery)."""

from __future__ import annotations

import pathlib

from ruamel.yaml import YAML

from coffer.domain.skill.external_dir import ExternalDirRegistration
from coffer.infrastructure.skill.external_dir_registrar import YamlExternalDirRegistrar


def _reg(tmp_path: pathlib.Path, *, dir_name: str = "ext") -> ExternalDirRegistration:
    return ExternalDirRegistration(
        config_path=tmp_path / "config.yaml",
        external_dir=tmp_path / dir_name,
        container_keys=("skills", "external_dirs"),
    )


def _dirs(path: pathlib.Path):
    data = YAML().load(path.read_text(encoding="utf-8")) or {}
    return (data.get("skills") or {}).get("external_dirs")


def test_register_creates_file_and_nested_keys(tmp_path):
    reg = _reg(tmp_path)
    YamlExternalDirRegistrar().register(reg)
    assert reg.config_path.exists()
    assert _dirs(reg.config_path) == [str(reg.external_dir)]


def test_register_is_idempotent(tmp_path):
    reg = _reg(tmp_path)
    r = YamlExternalDirRegistrar()
    r.register(reg)
    r.register(reg)
    assert _dirs(reg.config_path) == [str(reg.external_dir)]


def test_register_dedupes_by_resolved_path(tmp_path):
    reg = _reg(tmp_path)
    # Pre-seed the same directory in a non-normalised form.
    reg.config_path.write_text(
        f"skills:\n  external_dirs:\n    - {reg.external_dir}/../{reg.external_dir.name}\n",
        encoding="utf-8",
    )
    YamlExternalDirRegistrar().register(reg)
    # The equivalent path is recognised; no duplicate appended.
    assert len(_dirs(reg.config_path)) == 1


def test_register_appends_and_preserves_comments(tmp_path):
    reg = _reg(tmp_path)
    reg.config_path.write_text(
        "# top comment\nmodel: x\nskills:\n  external_dirs:\n    - ~/mine\n",
        encoding="utf-8",
    )
    YamlExternalDirRegistrar().register(reg)
    text = reg.config_path.read_text(encoding="utf-8")
    assert "# top comment" in text
    assert "model: x" in text
    assert _dirs(reg.config_path) == ["~/mine", str(reg.external_dir)]


def test_deregister_removes_entry_and_prunes_empty(tmp_path):
    reg = _reg(tmp_path)
    r = YamlExternalDirRegistrar()
    r.register(reg)
    r.deregister(reg)
    data = YAML().load(reg.config_path.read_text(encoding="utf-8")) or {}
    # The now-empty external_dirs list and its empty skills map are pruned.
    assert "skills" not in data


def test_deregister_keeps_other_entries(tmp_path):
    reg = _reg(tmp_path)
    reg.config_path.write_text(
        f"skills:\n  external_dirs:\n    - ~/mine\n    - {reg.external_dir}\n",
        encoding="utf-8",
    )
    YamlExternalDirRegistrar().deregister(reg)
    assert _dirs(reg.config_path) == ["~/mine"]


def test_deregister_missing_file_is_noop(tmp_path):
    reg = _reg(tmp_path)
    YamlExternalDirRegistrar().deregister(reg)  # must not raise
    assert not reg.config_path.exists()


def test_malformed_yaml_is_left_untouched(tmp_path):
    reg = _reg(tmp_path)
    original = "skills: : : not valid yaml :::\n"
    reg.config_path.write_text(original, encoding="utf-8")
    YamlExternalDirRegistrar().register(reg)
    # Never clobber a file we can't parse.
    assert reg.config_path.read_text(encoding="utf-8") == original


def test_non_list_container_key_is_not_overwritten(tmp_path):
    reg = _reg(tmp_path)
    original = "skills:\n  external_dirs: not-a-list\n"
    reg.config_path.write_text(original, encoding="utf-8")
    YamlExternalDirRegistrar().register(reg)
    data = YAML().load(reg.config_path.read_text(encoding="utf-8"))
    assert data["skills"]["external_dirs"] == "not-a-list"
