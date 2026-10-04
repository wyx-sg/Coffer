// src/lib/hooks/useHandoffAutoSend.ts — send a self-sending hand-off once.
//
// A hand-off marked `autoSend` (Tidy, Tidy all) is sent as soon as the draft it
// seeded is ready, rather than waiting for the person to press Send (spec
// knowledge "Hand a tidy to the agent", memory "Hand a partition's tidying to
// the agent"). Each queued prompt is its own object, sent at most once: a
// re-render or a StrictMode re-run never creates a second conversation, while
// pressing Tidy again queues a new one. A refused create leaves the prompt in the
// composer for the person to send.
import { useEffect, useRef } from "react";

/** @ui-only One prompt queued by a self-sending hand-off. */
export interface QueuedPrompt {
  text: string;
}

/** Sends `queued` once `ready` (the draft's config has applied, so the send goes
 *  to the right agent); `onSent` runs once the conversation is created. */
export function useHandoffAutoSend(
  queued: QueuedPrompt | null,
  ready: boolean,
  send: (text: string) => Promise<boolean>,
  onSent: () => void,
): void {
  const handled = useRef<QueuedPrompt | null>(null);
  // The latest callbacks, so the effect sends on the draft's current config.
  const latest = useRef({ send, onSent });
  latest.current = { send, onSent };

  useEffect(() => {
    if (!queued || !ready || handled.current === queued) return;
    handled.current = queued;
    void latest.current.send(queued.text).then((created) => {
      if (created) latest.current.onSent();
    });
  }, [queued, ready]);
}
