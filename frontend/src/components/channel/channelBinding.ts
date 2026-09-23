// frontend/src/components/channel/channelBinding.ts
// What is left of a channel's machine binding (spec channels "Bind each channel
// to the one machine that runs it") once the part two features share moved to
// `@/lib/machineBinding`: the one rule that is the CHANNEL's and nobody
// else's — the daemon's own `runs_here` outranks anything this code could work
// out for itself.
//
// The shared module owns the four states, the pick-list, and the rule that an
// empty registry is not a fault. It does not own what those states mean here:
// a channel bound to nobody runs NOWHERE on purpose, because answering a
// platform twice cannot be walked back. That copy lives with the components.
//
// It stays a module, rather than a helper inside one component, because the
// list row's cell and the detail card must answer identically. A channel
// reading "unbound" in the table and "running fine" on its own page would be
// worse than either answer alone.
import { bindingState as machineBindingState, type BindingState } from "@/lib/machineBinding";

interface StateInput {
  /** This machine's id from `GET /sync/status`; null while it is unknown. */
  selfId: string | null;
  /** Every machine id the registry knows. */
  known: readonly string[];
  /** `ChannelStatus.runs_here` when a status has been fetched. */
  runsHere?: boolean;
}

/**
 * Which of the four states this channel's binding is in.
 *
 * `runsHere` outranks any comparison the shared rule could make, because it is
 * the daemon's own answer to the same question: a vault that has never
 * converged has no registry and may have no machine id to compare against, and
 * the daemon still knows perfectly well that the channel is its to run. It is
 * fed in as the id to compare against rather than short-circuiting the result,
 * so "somewhere else" and "nowhere at all" keep being told apart by the one
 * piece of code that knows the difference. `selfId` is the fallback for
 * surfaces that have the binding but no status.
 */
export function bindingState(
  boundId: string | null,
  { selfId, known, runsHere }: StateInput,
): BindingState {
  if (runsHere === undefined) return machineBindingState(boundId, { selfId, known });
  return machineBindingState(boundId, { selfId: runsHere ? boundId : null, known });
}
