// frontend/src/lib/hooks/useCredentialCheck.ts
//
// Check credentials as they are pasted (spec channels "Check credentials before
// they are saved"): once the person stops typing, the daemon asks the platform
// whether they work. Deliberately not a React Query query — the request holds a
// secret, and a query key would keep it in the cache for the session.
import { useEffect, useState } from "react";

import {
  validateCredentials,
  type CredentialCheck,
  type CredentialCheckRequest,
} from "@/lib/api/channels";

/** The hook's own state machine around the wire result. @ui-only */
export type CredentialCheckState =
  | { state: "idle" }
  | { state: "checking" }
  | { state: "done"; result: CredentialCheck };

const IDLE: CredentialCheckState = { state: "idle" };

/** `request` is `null` while there is nothing to check (nothing pasted yet). */
export function useCredentialCheck(
  request: CredentialCheckRequest | null,
  delayMs = 600,
): CredentialCheckState {
  const [state, setState] = useState<CredentialCheckState>(IDLE);
  // A string dependency, so a re-render with an equal request does not re-check.
  const key = request ? JSON.stringify(request) : null;

  useEffect(() => {
    if (key === null) {
      setState(IDLE);
      return;
    }
    let stale = false;
    setState({ state: "checking" });
    const timer = setTimeout(() => {
      validateCredentials(JSON.parse(key) as CredentialCheckRequest).then(
        (result) => {
          if (!stale) setState({ state: "done", result });
        },
        () => {
          // The daemon itself could not be asked: say the check was unreachable
          // rather than leave the field reading "Checking…".
          if (!stale) {
            setState({
              state: "done",
              result: {
                ok: false,
                reason: "unreachable",
                bot_handle: null,
                bot_name: null,
                same_bot: null,
                detail: null,
              },
            });
          }
        },
      );
    }, delayMs);
    return () => {
      stale = true;
      clearTimeout(timer);
    };
  }, [key, delayMs]);

  return state;
}
