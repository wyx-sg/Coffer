"""Filesystem mutations for memory projection (spec 007, agent layer).

The agent-side adapters own every native-file mutation; this module is their
only I/O surface. Two operations:

- ``symlink_with_migrate`` — replace an agent's native memory directory with a
  symlink to the canonical store, **merging** any pre-existing real files into
  the canonical store first so nothing is silently overwritten (Claude Code).
- ``write_managed_block`` / ``strip_managed_block`` — idempotently rewrite a
  marker-fenced block inside a file, leaving all content outside the markers
  untouched (Codex ``AGENTS.md``).

Pure stdlib filesystem code — no knowledge engines, so it stays out of the
engine-confinement contract. All paths are guarded against obvious traversal /
non-directory hazards; the helpers never overwrite a real file blindly.
"""

from __future__ import annotations

import os
import shutil
import tomllib
from pathlib import Path

from coffer.application.agent.projection.types import ProjectionFs, SymlinkOutcome


class ProjectionFsAdapter(ProjectionFs):
    """Concrete :class:`ProjectionFs` over the module-level helpers below.

    Injected into the adapters at the composition root so the agent application
    layer depends only on the port, not on this infrastructure module."""

    def symlink_with_migrate(self, *, canonical_dir: Path, link_path: Path) -> SymlinkOutcome:
        return symlink_with_migrate(canonical_dir=canonical_dir, link_path=link_path)

    def remove_symlink(self, *, link_path: Path) -> None:
        remove_symlink(link_path=link_path)

    def write_managed_block(
        self, *, file_path: Path, block_body: str, start_marker: str, end_marker: str
    ) -> str:
        return write_managed_block(
            file_path=file_path,
            block_body=block_body,
            start_marker=start_marker,
            end_marker=end_marker,
        )

    def strip_managed_block(self, *, file_path: Path, start_marker: str, end_marker: str) -> None:
        strip_managed_block(file_path=file_path, start_marker=start_marker, end_marker=end_marker)

    def disable_codex_memory(self, *, config_path: Path) -> bool:
        return disable_codex_memory(config_path=config_path)


#: The derived per-store index. It is regenerated from the fact files, so a
#: native copy is safe to discard on a name collision (it carries no unique
#: user content). Every other colliding file is preserved under a deduped name.
_DERIVED_INDEX_NAME = "MEMORY.md"


def symlink_with_migrate(*, canonical_dir: Path, link_path: Path) -> SymlinkOutcome:
    """Make ``link_path`` a directory symlink to ``canonical_dir``.

    If ``link_path`` is already the right symlink, this is a no-op. If it is a
    real directory holding files, those files are **moved** into
    ``canonical_dir`` first. A name collision never drops the incoming file: the
    canonical copy is kept and the incoming one is preserved alongside it under a
    deduped ``<stem>.imported-<n><suffix>`` name (the only exception is the
    derived ``MEMORY.md`` index, which is regenerated and safe to discard). The
    directory is removed and replaced by the symlink only after every real file
    has migrated, so nothing the user authored is ever lost (finding #3).
    """
    canonical_dir.mkdir(parents=True, exist_ok=True)
    link_path.parent.mkdir(parents=True, exist_ok=True)

    # Already the correct symlink → idempotent no-op.
    if link_path.is_symlink():
        try:
            if link_path.resolve() == canonical_dir.resolve():
                return SymlinkOutcome(target_path=str(link_path), merged_existing=False)
        except OSError:
            pass
        link_path.unlink()
        os.symlink(canonical_dir.resolve(), link_path, target_is_directory=True)
        return SymlinkOutcome(target_path=str(link_path), merged_existing=False)

    merged = False
    if link_path.exists():
        if not link_path.is_dir():
            raise NotADirectoryError(
                f"refusing to replace non-directory native memory path: {link_path}"
            )
        merged = _merge_dir_into(link_path, canonical_dir)
        shutil.rmtree(link_path)

    os.symlink(canonical_dir.resolve(), link_path, target_is_directory=True)
    return SymlinkOutcome(target_path=str(link_path), merged_existing=merged)


def _merge_dir_into(source: Path, dest: Path) -> bool:
    """Move every real file under ``source`` into ``dest`` without overwriting.

    Returns True if at least one file was migrated. Existing ``dest`` files win
    on a name collision (a canonical fact is never clobbered); the incoming file
    is preserved alongside it under a deduped name rather than dropped, so the
    user never loses a real file when the directory is later removed. The single
    exception is the derived ``MEMORY.md`` index, which is regenerated from the
    fact files and therefore safe to discard on collision (finding #3).
    """
    moved_any = False
    dest.mkdir(parents=True, exist_ok=True)
    for entry in sorted(source.rglob("*")):
        if not entry.is_file():
            continue
        rel = entry.relative_to(source)
        target = dest / rel
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(entry), str(target))
            moved_any = True
            continue
        # Collision. The derived index carries no unique content → discard it.
        if rel.name == _DERIVED_INDEX_NAME:
            entry.unlink()
            continue
        # Preserve the incoming file under a deduped name (canonical copy wins).
        deduped = _dedup_path(target)
        deduped.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(entry), str(deduped))
        moved_any = True
    return moved_any


def _dedup_path(target: Path) -> Path:
    """A non-existing sibling of ``target`` named ``<stem>.imported-<n><suffix>``."""
    n = 1
    while True:
        candidate = target.with_name(f"{target.stem}.imported-{n}{target.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def remove_symlink(*, link_path: Path) -> None:
    """Remove a projection symlink (leaving the canonical store intact).

    Only removes ``link_path`` when it is actually a symlink — a real directory
    is left alone so we never delete a user's files on un-projection.
    """
    if link_path.is_symlink():
        link_path.unlink()


def write_managed_block(
    *, file_path: Path, block_body: str, start_marker: str, end_marker: str
) -> str:
    """Idempotently write ``block_body`` between the markers in ``file_path``.

    Content outside the markers is preserved byte-for-byte. If the file has no
    managed block yet, one is appended. Returns the resulting file text.
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    existing = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
    block = f"{start_marker}\n{block_body.rstrip()}\n{end_marker}"
    new_text = _replace_block(existing, block, start_marker, end_marker)
    file_path.write_text(new_text, encoding="utf-8")
    return new_text


def strip_managed_block(*, file_path: Path, start_marker: str, end_marker: str) -> None:
    """Remove the managed block (and only it) from ``file_path`` if present."""
    if not file_path.exists():
        return
    existing = file_path.read_text(encoding="utf-8")
    stripped = _remove_block(existing, start_marker, end_marker)
    file_path.write_text(stripped, encoding="utf-8")


def _replace_block(text: str, block: str, start_marker: str, end_marker: str) -> str:
    start = text.find(start_marker)
    if start == -1:
        prefix = text.rstrip("\n")
        sep = "\n\n" if prefix else ""
        return f"{prefix}{sep}{block}\n"
    end = text.find(end_marker, start)
    if end == -1:
        # Dangling start marker — replace from the start marker to EOF.
        return text[:start] + block + "\n"
    end_full = end + len(end_marker)
    return text[:start] + block + text[end_full:]


def disable_codex_memory(*, config_path: Path) -> bool:
    """Set ``[memories] enabled = false`` in Codex's ``config.toml`` so it does
    not accumulate a divergent native copy.

    Best-effort + idempotent: writes a minimal table if the file/key is absent,
    rewrites only the ``enabled`` line if the table exists; all other content is
    preserved. Returns whether native memory is (now) disabled.
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)
    existing = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    try:
        parsed = tomllib.loads(existing) if existing.strip() else {}
    except tomllib.TOMLDecodeError:
        parsed = {}
    memories = parsed.get("memories")
    if isinstance(memories, dict) and memories.get("enabled") is False:
        return True  # already disabled — idempotent
    if "[memories]" in existing:
        new_text = _set_memories_disabled(existing)
    else:
        sep = "\n\n" if existing.rstrip() else ""
        new_text = f"{existing.rstrip()}{sep}[memories]\nenabled = false\n"
    config_path.write_text(new_text, encoding="utf-8")
    return True


def _set_memories_disabled(toml_text: str) -> str:
    """Ensure ``[memories]`` has ``enabled = false`` (line-level, idempotent)."""
    lines = toml_text.splitlines()
    out: list[str] = []
    in_memories = False
    saw_enabled = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_memories and not saw_enabled:
                out.append("enabled = false")
            in_memories = stripped == "[memories]"
            saw_enabled = False
            out.append(line)
            continue
        # Exact key match: ``startswith("enabled")`` would also clobber a
        # sibling key like ``enabled_extra`` (finding #8).
        if in_memories and stripped.split("=", 1)[0].strip() == "enabled":
            out.append("enabled = false")
            saw_enabled = True
            continue
        out.append(line)
    if in_memories and not saw_enabled:
        out.append("enabled = false")
    return "\n".join(out).rstrip() + "\n"


def _remove_block(text: str, start_marker: str, end_marker: str) -> str:
    start = text.find(start_marker)
    if start == -1:
        return text
    end = text.find(end_marker, start)
    if end == -1:
        return text[:start].rstrip("\n") + "\n"
    end_full = end + len(end_marker)
    # Drop the block plus any immediately-trailing newlines it owned, then
    # collapse a now-doubled blank gap left behind.
    before = text[:start].rstrip("\n")
    after = text[end_full:].lstrip("\n")
    if before and after:
        return f"{before}\n\n{after}"
    return (before or after).rstrip("\n") + ("\n" if (before or after) else "")
