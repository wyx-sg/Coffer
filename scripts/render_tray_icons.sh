#!/usr/bin/env bash
# Render the menu bar's template images from their SVG sources.
#
#   bash scripts/render_tray_icons.sh
#
# desktop/icons/tray/<name>.svg -> <name>.png (18 px, 1x) and <name>@2x.png
# (36 px). macOS draws a menu bar item 18 pt tall, so the 36 px image is the
# one a Retina display shows. Template images are black on transparent; macOS
# tints them for a light or a dark menu bar (spec desktop-app "Show the daemon
# and what needs the user in the menu bar"). The PNGs are checked in, so this
# runs only when an SVG changes. Needs `rsvg-convert` (brew install librsvg).
set -euo pipefail

cd "$(dirname "$0")/../desktop/icons/tray"
command -v rsvg-convert >/dev/null 2>&1 || {
	echo "render_tray_icons: rsvg-convert not found (brew install librsvg)" >&2
	exit 1
}
for svg in *.svg; do
	name="${svg%.svg}"
	rsvg-convert -w 18 -h 18 "$svg" -o "$name.png"
	rsvg-convert -w 36 -h 36 "$svg" -o "$name@2x.png"
	echo "render_tray_icons: $name.png, $name@2x.png"
done
