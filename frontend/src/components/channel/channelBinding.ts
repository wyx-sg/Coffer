// frontend/src/components/channel/channelBinding.ts
// The pure half of a channel's machine binding (spec channels, "Where a
// channel runs"): what a `runs_on` value IS from this machine's point of view,
// and the option list a picker offers for it.
//
// It is a module rather than two local helpers because the row cell and the
// detail card must answer both questions identically. A channel reading
// "unbound" in the table and "running fine" on its own page would be worse
// than either answer alone — the user would have to guess which surface to
// believe about a fact that decides whether the bot answers at all.
//
// The binding is NOT reach, and the two are easy to merge by accident. Reach
// (`enabled` + `scope`) says which AGENTS a channel may drive and is set per
// machine; the binding says which MACHINE runs the adapter and travels with
// the channel document to every machine. Nothing here touches `scope`.
import type { Machine } from "@/lib/api/sync";

/**
 * The four things a binding can be. `unknown` earns its own name because it is
 * the only one that is a FAULT: the channel names a machine nobody in the
 * registry claims, so no daemon will ever start it, and only a rebind fixes
 * that. Rendering it as a blank id — or worse, as an ordinary "runs elsewhere"
 * — would hide a channel that is dead everywhere.
 */
export type BindingState = "unbound" | "self" | "other" | "unknown";

/** One machine the picker can bind to, already resolved to what it displays. */
export interface MachineOption {
  id: string;
  /** The registry's display name; "" when nobody claims this id. */
  name: string;
  isSelf: boolean;
  /** False for an id carried only by the binding itself. */
  known: boolean;
}

interface StateInput {
  /** This machine's id from `GET /sync/status`; null while it is unknown. */
  selfId: string | null;
  /** Every machine id the registry knows. Empty on a vault that has never
   *  converged, which is why "not in the registry" alone cannot mean "fault". */
  known: readonly string[];
  /** `ChannelStatus.runs_here` when a status has been fetched. */
  runsHere?: boolean;
}

/**
 * Which of the four states this binding is in.
 *
 * `runsHere` outranks any comparison this function could make, because it is
 * the daemon's own answer to the same question: a vault that has never
 * converged has no registry and may have no machine id to compare against, and
 * the daemon still knows perfectly well that the channel is its to run.
 * `selfId` is the fallback for surfaces that have the binding but no status.
 */
export function bindingState(
  boundId: string | null,
  { selfId, known, runsHere }: StateInput,
): BindingState {
  if (boundId === null) return "unbound";
  if (runsHere ?? boundId === selfId) return "self";
  return known.includes(boundId) ? "other" : "unknown";
}

/**
 * What the picker may bind to.
 *
 * This machine is ALWAYS offered, even when the registry is empty: a
 * single-machine install has never converged and so has no registry at all,
 * and it must still be able to bind its own channels — the one install where
 * an empty pick-list would be fatal.
 *
 * A binding naming an id nobody claims is appended too, so the trigger keeps
 * reporting what is actually stored instead of falling back to a blank or, far
 * worse, to whichever machine happens to sort first.
 */
export function machineOptions(
  machines: readonly Machine[],
  selfId: string | null,
  boundId: string | null,
): MachineOption[] {
  const options: MachineOption[] = machines.map((m) => ({
    id: m.machine_id,
    name: m.name,
    isSelf: m.is_self,
    known: true,
  }));
  const has = (id: string) => options.some((o) => o.id === id);
  if (selfId !== null && !has(selfId)) {
    options.push({ id: selfId, name: "", isSelf: true, known: true });
  }
  if (boundId !== null && !has(boundId)) {
    options.push({ id: boundId, name: "", isSelf: false, known: false });
  }
  return options;
}
