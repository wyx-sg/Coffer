// Trade the one-time code `coffer open` put in the URL fragment for the API
// token, once, before the first render.
//
// The fragment is the channel because it never leaves the browser — it is not
// sent to the server, so it stays out of access logs and Referer headers. What
// travels there is a single-use code that expires in about a minute, not the
// token; see backend `web_session.py` for why that distinction matters.
//
// The fragment is stripped afterwards so a reload, a copied URL, or a
// screenshot does not carry a spent code around.

import { getCofferBaseUrl, setCofferToken } from "./auth";

const CODE_PARAM = "code";

/** The one-time code in `#code=…`, if this page was opened by `coffer open`. */
export function readCodeFromFragment(hash: string): string | null {
  const raw = hash.startsWith("#") ? hash.slice(1) : hash;
  if (!raw) return null;
  const code = new URLSearchParams(raw).get(CODE_PARAM);
  return code && code.length > 0 ? code : null;
}

/**
 * Exchange a fragment code for the API token and persist it.
 *
 * Returns true when a token was stored. Failure is deliberately quiet: a stale
 * or already-spent code just means the page falls back to whatever token
 * localStorage holds, and the app shows its normal unauthenticated state if
 * there is none. Throwing here would replace a recoverable state with a blank
 * screen.
 */
export async function consumeSignInCode(
  location: { hash: string },
  replaceHash: (url: string) => void,
): Promise<boolean> {
  const code = readCodeFromFragment(location.hash);
  if (code === null) return false;

  // Drop the code from the address bar first, so it is gone even if the
  // exchange below throws.
  replaceHash(window.location.pathname + window.location.search);

  try {
    const response = await fetch(`${getCofferBaseUrl()}/daemon/web-session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });
    if (!response.ok) return false;
    const { token } = (await response.json()) as { token?: string };
    if (!token) return false;
    setCofferToken(token);
    return true;
  } catch {
    return false;
  }
}
