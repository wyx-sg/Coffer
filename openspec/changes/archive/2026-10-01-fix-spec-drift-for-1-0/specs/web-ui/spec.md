## MODIFIED Requirements

### Requirement: Organise Settings into five tabs
Settings — the modal of "Open Settings as a modal from the sidebar footer" —
MUST carry exactly five tabs, in this order, grouped by what they manage rather
than by how Coffer is built, and MUST open on General:

- **General** (`/settings/general`) — display preferences (the interface language
  and the theme, the default page size and the preferred external editor), the
  **Coffer's model** section: the
  model Coffer's own engine runs on and the speech-to-text model (see "Choose
  Coffer's model in Settings › General"), and — only while the registry names
  an experimental feature — the Experimental features card (spec
  [experimental-features](../experimental-features/spec.md) "List and switch the features on the General tab").
- **Security** (`/settings/security`) — what is about this machine only: where
  the master encryption key lives — in a signed release its Keychain access
  group; in a development build the file `~/.coffer/master.key` or the login
  keychain, with the switch that moves it — with its backup, import and
  fingerprint; the daemon's access token (see "Show, copy and rotate the access
  token on Settings › Security"); and whether a secret waits for approval
  before it goes somewhere new. It lists and edits no stored secret; those are
  on the Secrets page (see "Manage stored secrets on the Secrets page").
- **Data** (`/settings/data`) — what Coffer stores, by kind: Vault, Local content, History
  and Rebuildable cache (see "Group the Data tab by what kind of data it is").
- **Daemon** (`/settings/daemon`) — the daemon's state and the controls a user
  needs for it (see "Show and manage the daemon on Settings → Daemon").
- **About** (`/settings/about`) — version, license, source, whether a newer
  version is available (see "Check for and install updates on Settings › About"),
  and a small **Copy diagnostics** action beside the version.

Clicking a tab
swaps the modal's right pane without a full page reload and without closing the
modal.

#### Scenario: settings layout uses the redesigned tabbed sidebar
- **GIVEN** the user navigates to `/settings`
- **WHEN** the route resolves
- **THEN** the Settings modal opens on the General tab
- **AND** the modal's tab list shows General, Security, Data, Daemon, and About — exactly those five, in that order — with the current route highlighted
- **AND** clicking a tab swaps the right pane content without a full page reload and the modal stays open

#### Scenario: the security tab keeps only machine-level settings
- **GIVEN** stored secrets cited by a registered MCP server and a model provider
- **WHEN** the user opens `/settings/security`
- **THEN** the tab shows where the master key lives and, in a development build, its move control, and the access token's Show, Copy and Rotate controls
- **AND** it lists no stored secret and offers no control that adds, reveals or deletes one

### Requirement: Keep daemon shutdown on the command line
No tab may expose a "Shutdown daemon" or "Stop daemon" control: stopping the
daemon from the web kills the very page it was asked from, and recovery then needs
a terminal anyway, where `coffer daemon stop` already is. Restarting is not
stopping — the desktop shell's restart waits for the replacement and hands the
page its connection (spec [desktop-app](../desktop-app/spec.md) "Restart by stopping the running daemon first").
The About tab MUST show the version (with the short commit a release build was
made from, when stamped), license, source, the data folder, the update check of "Check
for and install updates on Settings › About" and **Copy diagnostics** only —
which copies the version, release channel, host, daemon state and port, and
the enabled experimental features as plain text, and never a token or a
secret — with no release-channel control, no language picker (the
sidebar already switches language) and no installed-resource-kind list
(developer detail). Remaining jargon is rewritten in plain language (e.g.
"prune" is phrased as clearing expired data).

#### Scenario: settings offers no shutdown control
- **GIVEN** the user opens the Settings tabs
- **WHEN** each tab is fully rendered
- **THEN** no tab exposes a "Shutdown daemon" or "Stop daemon" control
- **AND** the About tab shows version / license / source / data folder, the update check and Copy diagnostics only — no language picker, no resource-kind list, no release channel
