// frontend/src/components/channel/channelHealth.ts
// One tone for a channel's run state, shared by the list's health badge and
// the detail page's Status card so the two surfaces never disagree about what
// "stopped" looks like. A live adapter is the healthy case; a stopped one is
// not an error — the channel may simply be disabled — but it wants attention,
// so it reads as warn rather than muted or the brand colour.
import { toneClass, type Tone } from "@/lib/statusColors";

function channelHealthTone(running: boolean): Tone {
  return running ? "ok" : "warn";
}

/** Badge class for a running / stopped state, on the shared status tokens. */
export function channelHealthClass(running: boolean): string {
  return toneClass(channelHealthTone(running));
}
