# Releasing Coffer

A release is a pushed `v*` tag; `.github/workflows/release.yml` builds and
publishes it. Without any of the credentials below it publishes an **unsigned**
release (`Coffer-unsigned-<triple>.dmg`, the quarantine step in the notes), and
the run page says which secret each skipped step was missing. This file is what
the owner does, once, to turn on Developer ID signing, notarisation and the
desktop app's auto-update — and what to check on every release after that. How
the pipeline works is in
[docs-site/architecture/distribution.md](docs-site/architecture/distribution.md#signing-notarisation-and-updates).

Never commit any of these values. Secrets go in **Settings → Secrets and
variables → Actions → Secrets**; the one public value goes in **Variables**.

## One-time setup

### 1. Apple Developer Program

- [ ] Enrol in the [Apple Developer Program](https://developer.apple.com/programs/)
      (paid, yearly) as the account that will own Coffer's signing identity.
- [ ] Note the **Team ID** (Membership details: ten letters and digits) and add
      it as the secret **`APPLE_TEAM_ID`**.

The Team ID also decides where the master key lives: the release stamps
`<TEAM_ID>.coffer` into `build_identity.KEYCHAIN_ACCESS_GROUP`
(`scripts/stamp_build_identity.py`), compiles it into the shell as
`COFFER_KEYCHAIN_ACCESS_GROUP`, and signs every binary with the
`keychain-access-groups` entitlement for it
(`desktop/entitlements/coffer.entitlements.in`). The three always agree because
they come from this one secret. **Changing the Team ID later moves the access
group**, and a signed build can then no longer read a key stored under the old
one: back up the master key (desktop app → Settings › Security) first.

### 2. Developer ID Application certificate

- [ ] In Keychain Access → Certificate Assistant, request a certificate from a
      certificate authority (saved to disk).
- [ ] On developer.apple.com → Certificates, create a **Developer ID
      Application** certificate from that request, download it and open it so
      it joins your login keychain with its private key.
- [ ] Export the certificate *with its private key* as a `.p12` with a strong
      export password.
- [ ] Add `base64 -i DeveloperID.p12 | pbcopy` as the secret
      **`APPLE_CERTIFICATE`** and the export password as
      **`APPLE_CERTIFICATE_PASSWORD`**.
- [ ] Optional, only if the first signed build shows the access-group
      entitlement needs one (see "First signed release" below): create a
      **Developer ID** provisioning profile for an App ID with the Keychain
      Sharing capability and add it base64-encoded as
      **`APPLE_PROVISIONING_PROFILE`**; the release embeds it in the app.

### 3. App Store Connect API key (notarisation)

- [ ] App Store Connect → Users and Access → Integrations → App Store Connect
      API → Team Keys: generate a key with the **Developer** role.
- [ ] Download `AuthKey_<KEYID>.p8` (it can be downloaded only once) and add
      `base64 -i AuthKey_<KEYID>.p8 | pbcopy` as the secret **`APPLE_API_KEY`**.
- [ ] Add the key's ID as **`APPLE_API_KEY_ID`** and the Issuer ID shown above
      the key list as **`APPLE_API_ISSUER`**.

Notarisation runs only when Developer ID signing does.

### 4. Updater key pair (auto-update)

- [ ] On a trusted machine: `npx @tauri-apps/cli signer generate -w ~/.tauri/coffer-updater.key`
      and choose a password. It writes the private key and `coffer-updater.key.pub`.
- [ ] Add the **contents** of the private key file as the secret
      **`TAURI_SIGNING_PRIVATE_KEY`** and its password as
      **`TAURI_SIGNING_PRIVATE_KEY_PASSWORD`**.
- [ ] Add the **contents** of `coffer-updater.key.pub` as the repository
      **variable** (not secret) **`COFFER_UPDATER_PUBKEY`**. It is compiled into
      every desktop app the release builds, which verifies each update against it.
- [ ] Keep an offline backup of the private key and its password. **Losing it
      strands every installed app**: they only accept updates signed by it, so a
      new key means every user installs a new `.dmg` by hand once.

The updater does not need Apple signing; it can be turned on first.

## Every release

- [ ] `python scripts/bump_version.py <version>` so the Python package, the
      frontend, `desktop/Cargo.toml` and `desktop/tauri.conf.json` agree (the
      app's update check compares against `tauri.conf.json`'s version).
- [ ] Merge to `main`, tag `v<version>`, push the tag.
- [ ] On the run page, read the three **plan release signing** annotations:
      each should say **ON**. A **SKIPPED** line names the missing secret.
- [ ] The release carries `coffer-cli-<triple>.tar.gz`,
      `Coffer-<triple>.dmg` (not `Coffer-unsigned-…`),
      `Coffer_<triple>.app.tar.gz`, its `.sig`, `latest.json` and `SHA256SUMS`.
- [ ] `latest.json` names the tag's version and a URL on this tag's release.
- [ ] Mark the release as the **latest** (not a pre-release): the app reads
      `releases/latest/download/latest.json`.

## First signed release

Checks the pipeline cannot make for itself, done once on a real Mac:

- [ ] Download the `.dmg` in a browser and open it: no "damaged" dialog, and
      `spctl -a -vv /Applications/Coffer.app` says *Notarized Developer ID*.
- [ ] `codesign -d --entitlements - /Applications/Coffer.app/Contents/MacOS/coffer-daemon`
      shows `keychain-access-groups` = `<TEAM_ID>.coffer`.
- [ ] Reveal a secret in the app: the Touch ID prompt no longer says
      **Development build**, and `~/.coffer/master.key` is gone because the
      master key moved into the Keychain.
      If the daemon cannot use the access group (a missing-entitlement error in
      `~/.coffer/logs/daemon.log`), add the provisioning profile (step 2) and
      follow the fallback in
      [docs/decisions/master-key-lives-in-the-macos-keychain.md](docs/decisions/master-key-lives-in-the-macos-keychain.md)
      ("To prove before acceptance").
- [ ] With the app of the previous signed release installed, publish the next
      one and choose **Download and restart** on Settings › About: the app
      relaunches on the new version and the daemon status reports it too. If the
      update is refused with a signed-version error, the Tauri CLI that signed
      it predates version signing; update `@tauri-apps/cli` in the workflow.
