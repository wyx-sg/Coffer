// The desktop window's chrome, seen from the page.
//
// On macOS the shell draws no title bar: the native traffic lights float over
// the app (`tauri.macos.conf.json`: overlay title bar, hidden title). The page
// must then keep its own top row clear of them and offer a strip to drag the
// window by. Everything keys off one attribute on <html> — `data-chrome=
// "overlay"` — which `index.css` turns into the `--titlebar-inset` variable;
// a browser tab, Windows and Linux never get it.

import { inDesktopShell } from "./tauri";

/** Height of the strip the traffic lights sit in, in px (matches index.css). */
export const TITLEBAR_INSET_PX = 44;

function isMac(): boolean {
  return typeof navigator !== "undefined" && /Mac/i.test(navigator.platform || navigator.userAgent);
}

/** True when the native title bar is replaced by traffic lights over the page. */
export function overlayTitleBar(): boolean {
  return inDesktopShell() && isMac();
}

/** Mark <html> once at startup; a no-op in a browser and off macOS. */
export function applyWindowChrome(): void {
  if (!overlayTitleBar()) return;
  document.documentElement.dataset.chrome = "overlay";
}
