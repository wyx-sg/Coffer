## MODIFIED Requirements

### Requirement: Open config files in an external editor or reveal them
The agent's **Config files** tab MUST be one split view, resizable by its divider (web-ui "Resize every split view by its divider"): a file tree on the left listing every allowlisted config file on disk — and, as a folder of its files, each directory entry — and the selected file read-only on the right, in the shared viewer whose toolbar shows the file's path and size with **Open in editor** and **Reveal in Finder**, using the `path` and `folder_path` from "List an agent's config files with their locations"; a Reveal icon in the tree's header reveals the config directory. Only what exists on disk is listed: a file or directory entry the agent has not created yet is left out of the tree, because opening creates nothing and Coffer creates no config file, and an agent with none on disk shows that no config file was found. The selected file is in the URL (`?file=`) and defaults to the first file listed. Open and reveal perform the real OS action through the daemon's filesystem-action endpoints (`POST /api/v1/fs/open`, `POST /api/v1/fs/reveal`, and the installed-editor enumeration `GET /api/v1/fs/editors` behind the preference — all owned by the daemon spec, which this spec consumes and does not specify), since the loopback daemon is always on the user's own machine ([Daemon Proxies OS File Actions](../../../docs/decisions/daemon-proxies-os-file-actions.md)). Selecting a file shows its read-only preview ("Preview an agent's config file read-only"); the tab offers no edit, new file or delete: a config file is changed in the person's own editor or by their agent. There is no copy-path fallback. The editor used for open-in-external-editor references the user's "preferred external editor" preference defined by web-ui (not re-specified here).

#### Scenario: open a config file and reveal it through the daemon
- **GIVEN** an agent's Config files tab listing an existing config file and one not created yet
- **WHEN** the user chooses Open in editor and then Reveal in Finder on the open file's toolbar
- **THEN** the UI asks the daemon to open that file's absolute path and then to reveal it
- **AND** the file not created yet is not listed in the tree, nothing offers Edit, New file or Delete, and no copy-path affordance is offered

#### Scenario: preview a config file from its row
- **GIVEN** an agent's Config files tab listing an existing `settings.json`
- **WHEN** the user selects the file in the tree
- **THEN** the right pane shows the file's content read-only
- **AND** the pane offers Open in editor and Reveal in Finder and no Edit or Save
