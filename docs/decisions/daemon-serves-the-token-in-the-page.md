# The Daemon Serves Its Token in the Page, Guarded by the Host Header

> 中文版: [daemon-serves-the-token-in-the-page.zh.md](./daemon-serves-the-token-in-the-page.zh.md)

- **Status:** Accepted
- **Date:** 2026-09-11
- **Deciders:** Yuxing Wu
- **Spec:** [mcp-gateway](../../specs/mcp-gateway/spec.md) FR-024 / FR-025 / FR-027
- **Related:** [Detect-or-Spawn](./daemon-detect-or-spawn.md) (the daemon's port moves between restarts, which is the other half of why a browser could not find its way back)

## Context

The daemon mints a new API token on every start — `secrets.token_urlsafe(32)`,
never persisted across restarts — and binds the first free port in its range, so
the origin can move too. The browser's only way to obtain that token was a
one-time `#code=…` fragment that `coffer open` put in the launch URL: the page
traded the code for the token at `POST /daemon/web-session` and kept the token in
`localStorage`.

That works exactly once per `coffer open`. Every other way a person arrives at
the UI — a bookmark, a typed address, a reload, a tab restored after sleep —
re-reads whatever `localStorage` still holds, which after any daemon restart is
a dead token. Every API call then 401s. The UI reported this as
`UNAUTHENTICATED`, whose copy called it a connectivity problem and advised a
refresh; a refresh re-reads the same dead token, so the advice could never work.
The real recovery was to run `coffer open` again, which nothing told the user.

The original design's premise is stated in the module it justified: "the URL is
the only channel a freshly-opened browser will read." That premise is wrong.
The daemon serves the SPA itself (FR-024), so the **response body** is a channel
to that browser — one the URL rules do not touch.

## Decision

**The daemon injects its live API token into the `index.html` it serves**, as
`window.__COFFER_TOKEN__` in the document head — the global the frontend already
preferred over storage, because that is how the Vite dev server supplies it. A
page the daemon served is therefore authenticated by the act of being served,
with no user action and nothing persisted.

Three properties make it correct rather than merely convenient:

- **One source of truth.** The injected value comes from
  `surfaces/http/auth.get_active_token()` — the same in-process variable
  `require_token` compares against, read per request. A rotation republishes
  that one variable, so what the page is handed cannot drift from what the API
  accepts.
- **Every route, not just `/`.** The injection happens wherever `index.html` is
  served, including the SPA fallback for client-side routes. The failure that
  prompted this was on `/agents`.
- **Never cached.** The document now carries a per-daemon secret, so it is
  served `Cache-Control: no-store` with no ETag and no Last-Modified. A cached
  or revalidated copy would hand a restarted daemon's browser the previous
  daemon's token — the bug, reintroduced through the cache. Hashed files under
  `/assets` keep normal caching.

**And the daemon refuses any request whose `Host` header is not a loopback
authority** (FR-027), answering `421 HOST_NOT_LOOPBACK`. This is not an
independent tidy-up; it is what makes the injection safe, and neither half
ships without the other.

Binding to loopback stops a remote host. It does not stop a browser: a page on
`evil.com` whose hostname the attacker re-resolves to `127.0.0.1` is, to the
browser, still same-origin with `evil.com` — so CORS never applies and the page
can read the response body. Before this change that bought nothing, because the
daemon's HTML held no secret. With the token in the document, one `fetch("/")`
would have taken the whole vault. DNS rebinding does not alter the `Host`
header, so a rebound request still says `Host: evil.com` and is refused.

`COFFER_ALLOWED_HOSTS` (comma-separated, or `*`) adds authorities. The backend
test suite sets `*` because it drives the ASGI app in-process, where there is no
network and no browser; nothing in a real deployment needs it.

The one-time-code path is deleted rather than left beside the new one: the
`web_session` store, `POST /daemon/web-code`, `POST /daemon/web-session`, the
frontend exchange, and the `coffer.token` localStorage key are all gone.
`coffer open` remains, carrying no credential — it reads the daemon's real port
from `daemon.json` (and detect-or-spawn starts one if needed) and opens the
browser at that origin.

## Consequences

- **The UI recovers by itself.** Restart the daemon, reload the page — even on a
  deep link — and it is authenticated against the new daemon on its new port.
  The `coffer open`-after-every-restart ritual is gone.
- **Nothing about the session is persisted.** No token in storage, none in a
  URL, none in history. The page's credential lives as long as the document.
- **The `Host` check is now load-bearing.** Any future surface reachable on the
  daemon's port inherits it. The separate `coffer-callback` process — the only
  thing a tunnel is ever pointed at — is a different app on a different port and
  is unaffected; it authenticates inbound traffic by per-channel signature and
  forwards to the daemon over loopback.
- **A browser that is not served by the daemon has no token.** That is the Vite
  dev server, which already injects the same global from `daemon.json`. There is
  no third case.

## Alternatives considered

- **Keep the code exchange and only fix the error copy.** Rejected: it leaves
  the user re-running `coffer open` after every restart and merely explains the
  dead end more politely.
- **Persist the token across restarts instead of minting a new one.** Rejected:
  a long-lived on-disk token that unlocks the credential endpoints is a worse
  trade than a per-process one, and it would not fix the port drifting.
- **Put the token in the URL fragment directly.** Rejected for the original
  design's own reason — a URL reaches history, scrollback, screenshots and
  pasted bug reports. The response body reaches none of those, which is why it
  is the right channel and the fragment was not.
- **Rely on loopback binding alone and skip the `Host` check.** Rejected: that
  is precisely the gap DNS rebinding walks through, and it is the gap the
  injection would have opened.
