## ADDED Requirements

### Requirement: Preview an unmanaged skill read-only
Users MUST be able to open one unmanaged skill (see "List unmanaged skills in an agent's skill locations") and read it without adopting it: its metadata — name, path, location, `valid` with the failure reason, whether it is a foreign link, and the SKILL.md `description` when the folder validates — a recursive file tree of the folder, and the contents of each file. The entry is found by the same scan the list runs, addressed by the agent, the scan location and the folder name, so a name the scan does not list — a missing folder, a dot-entry, a Coffer-managed link — is not found. The tree and file reads MUST follow the containment, size cap and binary detection of "Show a skill's master folder read-only", rooted at the unmanaged folder: a path that resolves outside it (`..` traversal, an absolute path, an escaping symlink) is rejected with `400` before anything is read. Nothing here writes. An invalid folder MUST still open, with its reason. The preview is on REST (`GET /agents/{uid}/unmanaged-skills/{skill}`, `.../files`, `.../files/content`, each taking `location`), on the CLI (`coffer skill files|cat <name> --agent <agent> [--location …]`), and on the web as the unmanaged skill's detail page.

#### Scenario: preview an unmanaged skill's metadata and files
- **GIVEN** an agent whose skills directory holds a hand-placed skill folder with a valid SKILL.md and a nested file
- **WHEN** the user requests that folder's metadata, its file tree and its SKILL.md
- **THEN** the metadata carries the folder's name, path, location, `valid` true and the SKILL.md description
- **AND** the tree lists the folder's entries directories-first, and the file read returns the SKILL.md text, with the folder left unchanged

#### Scenario: an invalid unmanaged skill still opens and says why
- **GIVEN** an agent whose skills directory holds a folder without a valid SKILL.md
- **WHEN** the user opens it
- **THEN** its metadata carries `valid` false with the reason and no description, and its files are still listed
- **AND** the detail page shows the reason before anything else and offers no adoption

#### Scenario: reject reading a path outside an unmanaged skill folder
- **GIVEN** an unmanaged skill folder
- **WHEN** the user requests file contents for a path that resolves outside it (`..` traversal, an absolute path, or a symlink pointing out)
- **THEN** the request is rejected with a `400` error and no content is returned

#### Scenario: read an unmanaged skill's files from the command line
- **GIVEN** an agent with a hand-placed skill folder holding a nested file
- **WHEN** the user runs `coffer skill files <folder> --agent <agent>` and `coffer skill cat <folder> <path> --agent <agent> --json`
- **THEN** the first prints the folder's tree and the second the file's contents
- **AND** the folder is still listed as unmanaged afterwards

### Requirement: Act on an unmanaged skill from its detail page
The agent's Skills tab MUST open an unmanaged skill's detail page when its row is clicked; the rows carry Adopt and Delete and no Open folder. The detail page MUST show the skill's name with an Unmanaged badge and its location, a back link to the agent's Skills tab, and the actions Open folder (the folder in the OS file manager), Adopt ("Adopt an unmanaged skill"; disabled with its reason for an invalid folder or a foreign link) and Delete ("Delete an unmanaged skill on explicit request", confirmed first). A successful adoption MUST go on to the new managed skill's detail page, since the folder is no longer unmanaged; a successful delete MUST return to the agent's Skills tab.

#### Scenario: open an unmanaged skill's detail page from the agent's Skills tab
- **GIVEN** an agent's Skills tab listing unmanaged skills
- **WHEN** the user clicks one row
- **THEN** that skill's detail page opens, and its Files tab shows the folder's tree and a read-only preview of the chosen file
- **AND** no row in the table carries an Open folder button

#### Scenario: adopt or delete an unmanaged skill from its detail page
- **GIVEN** an unmanaged skill's detail page
- **WHEN** the user adopts it
- **THEN** the page moves to the new managed skill's detail page
- **AND** when the user instead deletes it and confirms, the folder is deleted and the page returns to the agent's Skills tab
