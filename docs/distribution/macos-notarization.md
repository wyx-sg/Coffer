# macOS Notarization

Until Coffer has a paid Apple Developer ID, the `.dmg` shipped from the
release workflow is **unsigned and unnotarized**. On macOS 10.15+ (Catalina
and later), Gatekeeper will quarantine the app on first open. Users can work
around this with either:

- **Right-click → Open** (bypasses Gatekeeper once for a specific app), or
- `xattr -d com.apple.quarantine /Applications/Coffer.app`

## Path to notarized builds

When the team has a paid Apple Developer ID enrolled in the Apple Developer
Program, follow the steps below to enable code signing and notarization in the
release workflow.

### 1. Generate a signing identity

In the [Apple Developer portal](https://developer.apple.com/account/resources/certificates/list):

1. Create a new certificate of type **"Developer ID Application"** for your
   team.
2. Download the `.cer` file and install it in Keychain Access.
3. Export the certificate + private key as a `.p12` with a strong password.
4. Base64-encode the `.p12`:
   ```bash
   base64 -i /path/to/cert.p12 | pbcopy
   ```

### 2. Create GitHub repository secrets

Add the following secrets under **Settings → Secrets and variables → Actions**:

| Secret name                  | Value                                                     |
| ---------------------------- | --------------------------------------------------------- |
| `APPLE_CERTIFICATE`          | Base64-encoded `.p12` content (from step 1)               |
| `APPLE_CERTIFICATE_PASSWORD` | The password you chose when exporting the `.p12`          |
| `APPLE_SIGNING_IDENTITY`     | `Developer ID Application: <Your Name or Org> (<TeamID>)` |
| `APPLE_ID`                   | Your Apple ID email address                               |
| `APPLE_PASSWORD`             | App-specific password from [appleid.apple.com][]          |
| `APPLE_TEAM_ID`              | 10-character team ID from the Apple Developer portal      |

[appleid.apple.com]: https://appleid.apple.com/account/manage

### 3. Configure Tauri to sign the bundle

**Add** a `macOS` key under `bundle` in `desktop/tauri.conf.json` (the `bundle`
block already exists — it currently has no `macOS` key):

```json
{
  "bundle": {
    "macOS": {
      "signingIdentity": null,
      "entitlements": "entitlements.plist"
    }
  }
}
```

Tauri reads `APPLE_SIGNING_IDENTITY` from the environment when
`signingIdentity` is `null` (Tauri 2 default behavior with env override).
Set it to the literal string only if the env var approach fails for your Tauri
version. The `entitlements` path wires the hardened-runtime entitlements that
already ship at `desktop/entitlements.plist` — they are required because the
bundled `coffer-daemon` / `coffer-mcp-shim` PyInstaller sidecars need
`disable-library-validation` and `allow-unsigned-executable-memory` to run
under the hardened runtime that notarisation mandates.

### 4. Add the codesign + notarize step to release.yml

`.github/workflows/release.yml` does **not** ship a disabled signing step today
— the `bundle` job carries only a comment block (between `install Tauri CLI` and
`cargo tauri build`) explaining that signing is deferred so the unused
`APPLE_*` secrets don't surface in repo-secret audits. To enable signing,
replace that comment block with the step below.

Signing spans two points in the job, in this order:

1. **Before `cargo tauri build`** (where the comment block sits today): import
   the certificate into a temporary keychain so the build can sign the `.app`.
   `cargo tauri build` reads `APPLE_SIGNING_IDENTITY` from the environment and
   code-signs the `.app` (with the entitlements from step 3) during the bundle
   phase, so add the step-5 `env:` block to the `cargo tauri build` step too.
2. **After `collect artifacts (macOS)`** (where the `.dmg` exists): notarise and
   staple it. Also drop the `-unsigned` rename in that collect step once builds
   are signed.

The combined step in step 5 keeps both halves together for readability; split
the keychain-import lines (before build) from the `notarytool` loop (after
collect) to honour that ordering.

### 5. Full codesign + notarize step

```yaml
- name: codesign + notarize
  if: startsWith(matrix.os, 'macos')
  env:
    APPLE_CERTIFICATE: ${{ secrets.APPLE_CERTIFICATE }}
    APPLE_CERTIFICATE_PASSWORD: ${{ secrets.APPLE_CERTIFICATE_PASSWORD }}
    APPLE_SIGNING_IDENTITY: ${{ secrets.APPLE_SIGNING_IDENTITY }}
    APPLE_ID: ${{ secrets.APPLE_ID }}
    APPLE_PASSWORD: ${{ secrets.APPLE_PASSWORD }}
    APPLE_TEAM_ID: ${{ secrets.APPLE_TEAM_ID }}
  run: |
    # Import the .p12 into a temporary keychain so it doesn't pollute the
    # macOS system keychain on the GitHub-hosted runner.
    KEYCHAIN_PASSWORD=$(openssl rand -base64 32)
    security create-keychain -p "$KEYCHAIN_PASSWORD" build.keychain
    security default-keychain -s build.keychain
    security unlock-keychain -p "$KEYCHAIN_PASSWORD" build.keychain
    echo "$APPLE_CERTIFICATE" | base64 -d > /tmp/cert.p12
    security import /tmp/cert.p12 -k build.keychain \
      -P "$APPLE_CERTIFICATE_PASSWORD" -T /usr/bin/codesign
    security set-key-partition-list \
      -S apple-tool:,apple: -s -k "$KEYCHAIN_PASSWORD" build.keychain

    # Notarize and staple each .dmg in the artifacts directory.
    # (cargo tauri build already code-signed the .app via APPLE_SIGNING_IDENTITY.)
    for dmg in artifacts/*.dmg; do
      xcrun notarytool submit "$dmg" \
        --apple-id  "$APPLE_ID" \
        --password  "$APPLE_PASSWORD" \
        --team-id   "$APPLE_TEAM_ID" \
        --wait
      xcrun stapler staple "$dmg"
    done

    # Clean up the temporary keychain.
    security delete-keychain build.keychain
```

> **Note**: `cargo tauri build` (run in the preceding step) picks up
> `APPLE_SIGNING_IDENTITY` from the environment and signs the `.app` bundle
> as part of the bundle phase. The notarytool step above runs _after_ `tauri
build` and submits the resulting `.dmg` to Apple's notarization service.

## Verifying a signed build

```bash
# Confirm the app is properly code-signed
codesign -dv --verbose=4 /Applications/Coffer.app

# Confirm Gatekeeper will allow execution without a quarantine prompt
spctl --assess --type execute --verbose /Applications/Coffer.app
```

Expected output from `spctl`:

```
/Applications/Coffer.app: accepted
source=Notarized Developer ID
```
