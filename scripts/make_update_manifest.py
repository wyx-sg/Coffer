#!/usr/bin/env python3
"""Write the desktop updater's manifest (``latest.json``) for one release.

    python scripts/make_update_manifest.py \
        --version 1.0.0 --platform darwin-aarch64 \
        --url https://github.com/<owner>/<repo>/releases/download/v1.0.0/<archive> \
        --signature-file Coffer.app.tar.gz.sig --notes-file notes.md --out latest.json

The release workflow runs it after ``tauri build`` has produced the updater
archive and signed it with the updater key (``TAURI_SIGNING_PRIVATE_KEY``). The
shell reads the manifest from the newest release
(``plugins.updater.endpoints`` in ``desktop/tauri.conf.json``) and installs the
archive only if its signature verifies against the public key built into it
(spec desktop-app "Check for updates against a signed release manifest"). The
manifest itself is not signed; the signature it carries covers the archive and,
with ``requireSignedVersion``, the version the archive was signed for.
Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

# The updater compares versions as semver; a leading `v` from the tag is not one.
_SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
_PLATFORM = re.compile(r"^(darwin|linux|windows)-(aarch64|x86_64|i686|armv7)$")


def manifest(
    *,
    version: str,
    platform: str,
    url: str,
    signature: str,
    notes: str = "",
    pub_date: datetime | None = None,
) -> dict[str, object]:
    """The manifest the updater plugin reads, for one platform."""
    version = version.removeprefix("v")
    if not _SEMVER.match(version):
        raise SystemExit(f"make_update_manifest: {version!r} is not a semver version")
    if not _PLATFORM.match(platform):
        raise SystemExit(f"make_update_manifest: {platform!r} is not an updater platform key")
    if not url.startswith("https://"):
        raise SystemExit("make_update_manifest: the archive URL must be https")
    signature = signature.strip()
    if not signature:
        raise SystemExit("make_update_manifest: the archive's signature is empty")
    when = (pub_date or datetime.now(UTC)).replace(microsecond=0)
    return {
        "version": version,
        "notes": notes.strip(),
        "pub_date": when.isoformat().replace("+00:00", "Z"),
        "platforms": {platform: {"signature": signature, "url": url}},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--version", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--signature-file", type=Path, required=True)
    parser.add_argument("--notes-file", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    notes = args.notes_file.read_text(encoding="utf-8") if args.notes_file else ""
    body = manifest(
        version=args.version,
        platform=args.platform,
        url=args.url,
        signature=args.signature_file.read_text(encoding="utf-8"),
        notes=notes,
    )
    args.out.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    print(f"make_update_manifest: {args.out} → {body['version']} for {args.platform}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
