# A Copied Secret Is Marked Concealed and Cleared After 90 Seconds

**Status**: Accepted
**Date**: 2026-11-06
**Deciders**: Yuxing Wu
**Related**: [Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md), spec secret "Release plaintext only to a present human in the desktop app"

## Context

A person reveals a secret in the desktop app behind Touch ID and can press Copy. Until now
the page copied with `navigator.clipboard.writeText`. That leaves the value on the macOS
general pasteboard until something replaces it, readable by any process of the same user
(the pasteboard is not access-controlled), and recorded by clipboard managers (Raycast,
Alfred, Paste, Maccy), which keep a history on disk. The reveal itself is gated; what the
person does with the copied value afterwards is not, so the copy undoes part of the gate.

How comparable products handle it (checked 2026-11-06):

- 1Password clears the clipboard after 90 seconds by default and marks the item with
  `org.nspasteboard.ConcealedType`.
- Bitwarden offers a clear-after setting (off by default on desktop, 10 s – 5 min).
- KeePassXC clears after 10 s by default and sets the concealed marker.
- macOS Keychain Access copies with no clearing and no marker.

The nspasteboard.org markers (`ConcealedType`: don't show or keep; `TransientType`: don't
record in history) are honoured by the common clipboard managers. A web page cannot set
them: `navigator.clipboard` writes plain text only.

## Options Considered

### Option A — Copy through the shell with both markers; clear after 90 s if unchanged (chosen)

A Tauri command (`copy_secret`) writes the value and both markers through `NSPasteboard`,
remembers the pasteboard's change count, and 90 seconds later clears it only if the count
is unchanged, so something the person copied since is never wiped.

- Pro: clipboard managers neither show nor store the value; it does not linger.
- Pro: matches what people know from 1Password; no setting to explain.
- Con: a small amount of Objective-C bridging in the shell; macOS only (the only platform
  that ships).

### Option B — Keep the page's copy, add a timer in the page that clears it

- Pro: no shell code.
- Con: no markers, so clipboard histories still keep the value forever.
- Con: the page can't tell whether the person copied something else since, so it might wipe
  their own clipboard; the timer dies with the dialog or window.

### Option C — Make the clear-after time a setting

- Con: one more setting for something nobody tunes; 1Password's default is the common
  expectation. Coffer stays lean, so no setting.

### Option D — Remove Copy, show the value only

- Con: a person who revealed a value almost always needs to paste it somewhere; they would
  retype or select-and-copy it, which goes through the page's copy anyway with neither
  protection.

## Decision

Option A. Both reveal dialogs copy through `copy_secret`. When the shell is absent or
refuses (not a Mac), the page falls back to its own clipboard write. The toast says the
clipboard is cleared in 90 seconds.

## Consequences

- A same-user process polling the pasteboard can still read the value during those 90
  seconds; that is inherent to a clipboard and outside what Coffer can close.
- The browser UI cannot reveal a secret at all, so it never needs the shell path.
