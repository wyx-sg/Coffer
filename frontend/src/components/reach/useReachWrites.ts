// frontend/src/components/reach/useReachWrites.ts
// The instant-save write queue of a ReachControl: optimistic view, queued
// writes, Saving… / Saved / failed state and the Retry of a rejected write.
//
// EVERY CHANGE SAVES AT ONCE (the instant variant, used by every single
// resource): each mode switch and each tick calls its callback immediately.
// The callbacks may return a promise; the footer shows Saving… / ✓ Saved /
// Couldn't save from it. The shown state is optimistic — it moves on the click,
// and snaps back if the write rejects, with the reason written inline (under
// the radios for a mode switch, under the row for a tick) beside a Retry; no
// toast. Writes are queued, so a second tick made while the first is in flight
// builds on the first rather than on a stale list.
import { useRef, useState, type Dispatch, type MutableRefObject, type SetStateAction } from "react";
import { useTranslation } from "react-i18next";

import type { SaveState } from "@/components/reach/ReachPanelFooter";
import { translateApiError } from "@/lib/api/errors";
import type { Scope } from "@/lib/hooks/useScope";
import type { ReachMode } from "@/lib/reach/reachState";

export type Write = () => void | Promise<unknown>;

export interface View {
  mode: ReachMode | null;
  scope: Scope | null;
}

export interface Failure {
  /** The agent whose tick failed; absent for a mode switch. */
  uid?: string;
  message: string;
  retry: () => void;
}

export function useReachWrites(
  viewRef: MutableRefObject<View>,
  setOverride: Dispatch<SetStateAction<View | null>>,
) {
  const { t } = useTranslation();
  const [save, setSave] = useState<SaveState>("idle");
  const [failure, setFailure] = useState<Failure | null>(null);
  const pending = useRef(0);
  const queue = useRef<Promise<void>>(Promise.resolve());

  const run = (next: View, write: Write, uid?: string) => {
    viewRef.current = next;
    setOverride(next);
    setSave("saving");
    setFailure(null);
    pending.current += 1;
    const exec = async () => {
      let ok = true;
      try {
        await write();
      } catch (error) {
        ok = false;
        setOverride(null);
        setFailure({
          uid,
          message: translateApiError(t, error),
          retry: () => run(next, write, uid),
        });
      }
      pending.current -= 1;
      setSave(ok ? (pending.current > 0 ? "saving" : "saved") : "failed");
    };
    // Idle: write in this very tick; busy: wait behind the writes in flight.
    queue.current = pending.current === 1 ? exec() : queue.current.then(exec);
  };

  return { save, setSave, failure, setFailure, pending, run };
}
