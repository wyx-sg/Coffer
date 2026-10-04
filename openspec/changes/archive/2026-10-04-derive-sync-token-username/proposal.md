## Why

The username git sends with an HTTPS token is fixed by the host, not chosen by
the person: Bitbucket expects `x-token-auth`, GitLab `oauth2`, and GitHub and
Azure DevOps ignore it. A **User name** field on the Remote tab asked people
for something the remote's URL already tells Coffer.

## What Changes

- **BREAKING** The sync remote has no username setting. The username sent with
  a token is derived from the URL's host: `x-token-auth` for `bitbucket.org`,
  `oauth2` for a host whose name contains `gitlab`, `coffer` otherwise.
- The **User name** field leaves the Remote tab, `username` leaves the sync
  remote API request and response and `local/sync/remote.json`, and the
  `--username` flag leaves `coffer sync remote set`.
- Bitbucket access tokens are supported; Bitbucket App passwords, which need
  the account's own name, are not.
- The MCP servers list's Built-in group header shows no count, and the sync
  rounds table footer always counts rounds ("Loaded 38 of 38 rounds", "Loaded
  20 of 38 rounds"), because rounds that repeat one outcome are folded into one
  row. These are presentation only and change no
  requirement.

## Impact

- `vault-sync` spec, `data-model.md`, the sync guide, architecture and
  reference pages (English and Chinese).
