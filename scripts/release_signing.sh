#!/usr/bin/env bash
# Developer ID signing and notarization for a release (macOS runners only).
#
#   release_signing.sh import-identity            # → $GITHUB_ENV: APPLE_SIGNING_IDENTITY
#   release_signing.sh render-entitlements <out>  # template with APPLE_TEAM_ID
#   release_signing.sh verify <binary>...         # Developer ID, hardened runtime, group
#   release_signing.sh verify-no-keychain <bin>... # Developer ID, hardened runtime, NO group
#   release_signing.sh notarize <file>            # notarytool submit --wait
#   release_signing.sh staple <file>              # stapler staple + validate
#   release_signing.sh cleanup                    # delete the temporary keychain
#
# The release workflow calls each subcommand only when scripts/release_plan.py
# found the credentials it needs, so nothing here has to decide whether to
# run. Credentials come from the environment, never from arguments, so they
# never reach the process list or the log:
#
#   APPLE_CERTIFICATE           base64 of the "Developer ID Application" .p12
#   APPLE_CERTIFICATE_PASSWORD  the .p12's export password
#   APPLE_TEAM_ID               the ten-character Team ID
#   APPLE_API_KEY               base64 of the App Store Connect API key (.p8)
#   APPLE_API_KEY_ID            that key's ID
#   APPLE_API_ISSUER            the issuer ID it belongs to
#
# RELEASING.md says how to create each one.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEMP="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
KEYCHAIN="$TEMP/coffer-signing.keychain-db"
TEMPLATE="$REPO_ROOT/desktop/entitlements/coffer.entitlements.in"

need() {
	for name in "$@"; do
		if [ -z "${!name:-}" ]; then
			echo "release_signing: $name is not set" >&2
			exit 1
		fi
	done
}

to_env() {
	# Export for the rest of the job, or print when run by hand.
	if [ -n "${GITHUB_ENV:-}" ]; then
		echo "$1=$2" >>"$GITHUB_ENV"
	else
		echo "$1=$2"
	fi
}

import_identity() {
	need APPLE_CERTIFICATE APPLE_CERTIFICATE_PASSWORD APPLE_TEAM_ID
	local p12 password identity
	p12="$TEMP/coffer-developer-id.p12"
	password="$(uuidgen)"
	echo "$APPLE_CERTIFICATE" | base64 --decode >"$p12"
	security create-keychain -p "$password" "$KEYCHAIN"
	security set-keychain-settings -lut 21600 "$KEYCHAIN"
	security unlock-keychain -p "$password" "$KEYCHAIN"
	security import "$p12" -k "$KEYCHAIN" -P "$APPLE_CERTIFICATE_PASSWORD" \
		-T /usr/bin/codesign -T /usr/bin/security
	security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$password" "$KEYCHAIN" >/dev/null
	# Search this keychain first, then the login keychain the runner already had.
	security list-keychains -d user -s "$KEYCHAIN" $(security list-keychains -d user | tr -d '"')
	rm -f "$p12"
	identity="$(security find-identity -v -p codesigning "$KEYCHAIN" |
		awk -F'"' -v team="($APPLE_TEAM_ID)" '/Developer ID Application/ && index($2, team) {print $2; exit}')"
	if [ -z "$identity" ]; then
		echo "release_signing: no 'Developer ID Application' identity for team $APPLE_TEAM_ID in the certificate" >&2
		exit 1
	fi
	echo "release_signing: signing as $identity"
	to_env APPLE_SIGNING_IDENTITY "$identity"
	to_env COFFER_CODESIGN_IDENTITY "$identity"
}

render_entitlements() {
	need APPLE_TEAM_ID
	local out="$1"
	if ! [[ "$APPLE_TEAM_ID" =~ ^[A-Z0-9]{10}$ ]]; then
		echo "release_signing: APPLE_TEAM_ID is not a ten-character Team ID" >&2
		exit 1
	fi
	sed "s/@TEAM_ID@/$APPLE_TEAM_ID/g" "$TEMPLATE" >"$out"
	plutil -lint "$out" >/dev/null
	echo "release_signing: entitlements for $APPLE_TEAM_ID.coffer → $out"
}

verify() {
	need APPLE_TEAM_ID
	local bin
	for bin in "$@"; do
		codesign --verify --strict --verbose=2 "$bin"
		local details
		details="$(codesign -d --verbose=4 "$bin" 2>&1)"
		grep -q "TeamIdentifier=$APPLE_TEAM_ID" <<<"$details" ||
			{ echo "release_signing: $bin is not signed by team $APPLE_TEAM_ID" >&2; exit 1; }
		grep -Eq "flags=.*runtime" <<<"$details" ||
			{ echo "release_signing: $bin is not signed under the hardened runtime" >&2; exit 1; }
		codesign -d --entitlements - --xml "$bin" 2>/dev/null | grep -q "$APPLE_TEAM_ID.coffer" ||
			{ echo "release_signing: $bin lacks the keychain-access-groups entitlement" >&2; exit 1; }
		if codesign -d --entitlements - --xml "$bin" 2>/dev/null | grep -q "get-task-allow"; then
			echo "release_signing: $bin carries get-task-allow" >&2
			exit 1
		fi
		echo "release_signing: $bin — Developer ID, hardened runtime, $APPLE_TEAM_ID.coffer"
	done
}

# The SeaTalk bridge runs operator-supplied code, so it must be signed like the
# others EXCEPT for the keychain group: prove the group is absent, both on the
# frozen binary and on the copy inside the built Coffer.app (which Tauri must
# not have re-signed with the app's entitlements).
verify_no_keychain() {
	need APPLE_TEAM_ID
	local bin details entitlements
	for bin in "$@"; do
		codesign --verify --strict --verbose=2 "$bin"
		details="$(codesign -d --verbose=4 "$bin" 2>&1)"
		grep -q "TeamIdentifier=$APPLE_TEAM_ID" <<<"$details" ||
			{ echo "release_signing: $bin is not signed by team $APPLE_TEAM_ID" >&2; exit 1; }
		grep -Eq "flags=.*runtime" <<<"$details" ||
			{ echo "release_signing: $bin is not signed under the hardened runtime" >&2; exit 1; }
		entitlements="$(codesign -d --entitlements - --xml "$bin" 2>/dev/null || true)"
		if grep -q "keychain-access-groups" <<<"$entitlements" || grep -q "$APPLE_TEAM_ID.coffer" <<<"$entitlements"; then
			echo "release_signing: $bin carries the keychain-access-groups entitlement" >&2
			exit 1
		fi
		if grep -q "get-task-allow" <<<"$entitlements"; then
			echo "release_signing: $bin carries get-task-allow" >&2
			exit 1
		fi
		echo "release_signing: $bin — Developer ID, hardened runtime, no keychain group"
	done
}

api_key_file() {
	need APPLE_API_KEY APPLE_API_KEY_ID APPLE_API_ISSUER
	local key="$TEMP/AuthKey_${APPLE_API_KEY_ID}.p8"
	[ -f "$key" ] || echo "$APPLE_API_KEY" | base64 --decode >"$key"
	echo "$key"
}

notarize() {
	local file="$1" key submit
	key="$(api_key_file)"
	submit="$file"
	case "$file" in
	*.dmg | *.zip | *.pkg) ;;
	*)
		# A bare binary or a .app goes to the notary service as a zip.
		submit="$TEMP/$(basename "$file").zip"
		ditto -c -k --keepParent "$file" "$submit"
		;;
	esac
	local result status id
	result="$(xcrun notarytool submit "$submit" --key "$key" --key-id "$APPLE_API_KEY_ID" \
		--issuer "$APPLE_API_ISSUER" --wait --output-format json)"
	status="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("status",""))' <<<"$result")"
	id="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("id",""))' <<<"$result")"
	if [ "$status" != "Accepted" ]; then
		echo "release_signing: notarization of $file ended $status" >&2
		xcrun notarytool log "$id" --key "$key" --key-id "$APPLE_API_KEY_ID" --issuer "$APPLE_API_ISSUER" >&2 || true
		exit 1
	fi
	echo "release_signing: $file notarized ($id)"
}

staple() {
	xcrun stapler staple "$1"
	xcrun stapler validate "$1"
	echo "release_signing: $1 stapled"
}

cleanup() {
	security delete-keychain "$KEYCHAIN" 2>/dev/null || true
	rm -f "$TEMP"/AuthKey_*.p8
}

cmd="${1:-}"
shift || true
case "$cmd" in
import-identity) import_identity ;;
render-entitlements) render_entitlements "$@" ;;
verify) verify "$@" ;;
verify-no-keychain) verify_no_keychain "$@" ;;
notarize) notarize "$@" ;;
staple) staple "$@" ;;
cleanup) cleanup ;;
*)
	echo "usage: release_signing.sh {import-identity|render-entitlements <out>|verify <bin>...|verify-no-keychain <bin>...|notarize <file>|staple <file>|cleanup}" >&2
	exit 2
	;;
esac
