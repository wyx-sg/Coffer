"""PLUGIN_DROP file mechanics for :class:`AgentHookService` — per PluginFlavor.

Split out of ``hook_service.py`` for the file-size limit (precedent:
``allowlists.py``). The service resolves specs, audits, and reports status;
these helpers own *what lands on disk* for each :class:`PluginFlavor`:

- ``OPENCODE`` — one flat ``coffer-session-context.js`` in the auto-loaded
  ``plugin/`` directory (rendering in ``domain/agent/plugin_drop``).
- ``OPENCLAW`` — a package directory ``extensions/coffer-session-context/``
  (three files, rendering in ``domain/agent/plugin_drop_openclaw``) PLUS the
  ``plugins.entries.<id>.enabled: true`` flag in ``openclaw.json`` (non-bundled
  openclaw plugins are fail-closed), whose spec the caller passes as
  ``enable_spec``. Uninstall removes the whole package tree with no ``.bak`` —
  the content is Coffer-rendered and regenerates byte-identically, and a
  leftover ``.bak`` package would still be discovered by openclaw's extension
  scanner.
"""

from __future__ import annotations

import pathlib

from coffer.application.agent.config_file_service import ConfigFileStorePort
from coffer.domain.agent.config_files import ConfigFileSpec
from coffer.domain.agent.context_injection import ContextInjectionSpec, PluginFlavor
from coffer.domain.agent.plugin_drop import PLUGIN_FILENAME, render_plugin
from coffer.domain.agent.plugin_drop_openclaw import (
    OPENCLAW_ENTRY_FILENAME,
    OPENCLAW_PLUGIN_ID,
    apply_entry_enable,
    apply_entry_remove,
    has_entry,
    render_openclaw_extension,
)


def plugin_marker_path(spec: ConfigFileSpec, inj: ContextInjectionSpec) -> pathlib.Path:
    """The file whose presence == "Coffer's plugin is installed".

    opencode: the dropped file itself. openclaw: the package's entry module
    (the file that actually runs — a gutted package without it is "absent").
    """
    if inj.plugin_flavor is PluginFlavor.OPENCLAW:
        return spec.path / OPENCLAW_PLUGIN_ID / OPENCLAW_ENTRY_FILENAME
    return spec.path / PLUGIN_FILENAME


def install_plugin_files(
    store: ConfigFileStorePort,
    spec: ConfigFileSpec,
    inj: ContextInjectionSpec,
    *,
    hook_binary: str,
    agent_name: str,
    enable_spec: ConfigFileSpec | None,
) -> pathlib.Path:
    """Write the flavor's plugin file(s); returns the path install audits.

    Idempotent — Coffer's own namespace (the flat file / the package dir) is
    overwritten in place, never duplicated, and no other file in the plugin
    directory is touched.
    """
    if inj.plugin_flavor is PluginFlavor.OPENCLAW:
        package_dir = spec.path / OPENCLAW_PLUGIN_ID
        files = render_openclaw_extension(hook_binary=hook_binary, agent_name=agent_name)
        for filename, content in files.items():
            store.write_text_atomic(package_dir / filename, content)
        # Fail-closed: without the entries flag openclaw ignores the package.
        assert enable_spec is not None  # descriptor declares plugin_enable_config_key
        text = store.read_text(enable_spec.path) or ""
        new_text = apply_entry_enable(text)
        if new_text != text:
            store.write_text_atomic(enable_spec.path, new_text)
        return package_dir
    path = spec.path / PLUGIN_FILENAME
    store.write_text_atomic(path, render_plugin(hook_binary=hook_binary, agent_name=agent_name))
    return path


def uninstall_plugin_files(
    store: ConfigFileStorePort,
    spec: ConfigFileSpec,
    inj: ContextInjectionSpec,
    *,
    enable_spec: ConfigFileSpec | None,
) -> tuple[bool, pathlib.Path]:
    """Remove the flavor's plugin file(s); returns ``(removed_anything, path)``.

    ``removed_anything=False`` means the uninstall was a no-op (nothing was
    installed) — the caller then skips the audit event. Only Coffer's own
    file/package (and, for openclaw, its own ``plugins.entries`` key) is
    touched.
    """
    if inj.plugin_flavor is PluginFlavor.OPENCLAW:
        package_dir = spec.path / OPENCLAW_PLUGIN_ID
        removed = store.remove_tree(package_dir)
        if enable_spec is not None:
            text = store.read_text(enable_spec.path)
            # Semantic no-op guard: only rewrite the config when Coffer's
            # entries key is actually present — a file that merely serializes
            # differently must not be reformatted (or audited) by a no-op.
            if text is not None and has_entry(text):
                store.write_text_atomic(enable_spec.path, apply_entry_remove(text))
                removed = True
        return removed, package_dir
    path = spec.path / PLUGIN_FILENAME
    return store.delete_with_backup(path), path


__all__ = ["install_plugin_files", "plugin_marker_path", "uninstall_plugin_files"]
