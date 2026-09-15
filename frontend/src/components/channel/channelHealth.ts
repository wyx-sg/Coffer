// frontend/src/components/channel/channelHealth.ts
// One tone for a channel's run state, shared by the list's health badge and
// the detail page's Status / callback cards so the two surfaces never disagree
// about what "stopped" looks like. A live adapter (or listener, or tunnel) is
// the healthy case; a stopped one is not an error — the channel may simply be
// disabled — but it wants attention, so it reads as warn rather than muted or
// the brand colour.
import { toneClass, type Tone } from "@/lib/statusColors";

export function channelHealthTone(running: boolean): Tone {
  return running ? "ok" : "warn";
}

/** Badge class for a running / stopped state, on the shared status tokens. */
export function channelHealthClass(running: boolean): string {
  return toneClass(channelHealthTone(running));
}
