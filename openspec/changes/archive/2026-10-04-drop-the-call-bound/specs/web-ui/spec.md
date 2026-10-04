## MODIFIED Requirements

### Requirement: Organise Settings into six tabs
Settings — the modal of "Open Settings as a modal from the sidebar footer" —
MUST carry six tabs, in this order, in every build, grouped by what they manage
rather than by how Coffer is built, and MUST open on General:

- **General** (`/settings/general`) — display preferences (the interface language
  and the theme, the default page size and the preferred external editor), and a
  **Speech-to-text** section: the connection and model that transcribe voice
  messages (spec [internal-engine](../internal-engine/spec.md) "Show the speech-to-text pair in Settings › General").
  It carries no experimental-features card; the switches are on the Features
  tab. While `models` is off the connection choice for speech-to-text is left out.
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
- **Features** (`/settings/features`) — the four experimental features, each
  marked Experimental, with its switch (spec
  [experimental-features](../experimental-features/spec.md) "Show the Features tab in every build").
- **About** (`/settings/about`) — version, license, source, whether a newer
  version is available (see "Check for and install updates on Settings › About"),
  and a small **Copy diagnostics** action beside the version.

Clicking a tab
swaps the modal's right pane without a full page reload and without closing the
modal.

Every pane follows the page grammar: it opens with the tab's title (an `h1`) and
one muted intro line, then its sections 32px apart. A section is not boxed — its
title carries its meta and action on one line, its description is one muted line
under the title, and its rows are separated by hairlines; a tab with a single
section (Features) prints no section title. Settings save on change: no pane has
a Save button, and a text field applies on Enter or when it loses focus.

#### Scenario: settings layout uses the redesigned tabbed sidebar
- **GIVEN** the user navigates to `/settings`
- **WHEN** the route resolves
- **THEN** the Settings modal opens on the General tab
- **AND** the modal's tab list shows General, Security, Data, Daemon, Features and About — exactly those six, in that order — with the current route highlighted
- **AND** clicking a tab swaps the right pane content without a full page reload and the modal stays open

#### Scenario: every settings tab opens with its title and an intro line
- **GIVEN** the Settings modal
- **WHEN** each of the six tabs is opened
- **THEN** its pane starts with an `h1` named for the tab, followed by one intro line
- **AND** the pane has no Save button

#### Scenario: the security tab keeps only machine-level settings
- **GIVEN** stored secrets cited by a registered MCP server and a model provider
- **WHEN** the user opens `/settings/security`
- **THEN** the tab shows where the master key lives and, in a development build, its move control, and the access token's Show, Copy and Rotate controls
- **AND** it lists no stored secret and offers no control that adds, reveals or deletes one
