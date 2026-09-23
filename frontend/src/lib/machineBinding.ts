// frontend/src/lib/machineBinding.ts
// The pure half of "which machine does this?" — what a stored machine id IS
// from where you are standing, and the option list a picker may offer for it.
//
// It started as the channel binding's own helper (spec channels "Bind each
// channel to the one machine that runs it"). It lives in `lib/` now because a
// second feature asks the same question of the same registry: the curation
// pass names one machine allowed to rewrite the derived documents (spec
// knowledge), and a vault whose owner is a machine nobody claims is dead in
// exactly the way a channel bound to one is. Two copies of this rule would let
// one surface call that a fault and the other call it normal.
//
// What it deliberately does NOT carry is what each feature MEANS by the four
// states. A channel with no binding runs NOWHERE — answering a platform twice
// cannot be walked back, so it fails closed. Curation with no owner runs
// HERE — a vault that never named one is a vault with one machine, and being
// wrong costs a duplicated document, not a bot talking to itself. The states
// are shared; the labels and the consequences belong to the feature.
//
// It is also not reach. Reach (`enabled` + `scope`) says which AGENTS a
// resource may drive and is set per machine; a binding says which MACHINE
// does the work and travels with the document to every machine.
import type { Machine } from "@/lib/api/sync";

/**
 * The four things a machine binding can be. `unknown` earns its own name
 * because it is the only one that is a FAULT: the binding names a machine
 * nobody in the registry claims, so no daemon will ever act on it, and only a
 * rebind fixes that. Rendering it as a blank id — or worse, as an ordinary
 * "runs elsewhere" — would hide work that happens nowhere at all.
 */
export type BindingState = "unbound" | "self" | "other" | "unknown";

/** One machine a picker can bind to, already resolved to what it displays. */
export interface MachineOption {
  id: string;
  /** The registry's display name; "" when nobody claims this id. */
  name: string;
  isSelf: boolean;
  /** False for an id carried only by the binding itself. */
  known: boolean;
}

export interface BindingInput {
  /** This machine's id from `GET /sync/status`; null while it is unknown. */
  selfId: string | null;
  /** Every machine id the registry knows. Empty on a vault that has never
   *  converged, which is why "not in the registry" alone cannot mean "fault". */
  known: readonly string[];
}

/**
 * Which of the four states a stored machine id is in, seen from here.
 *
 * An empty registry can never produce `unknown` for this machine's own id: a
 * single-machine install has never converged and so has no registry, and the
 * one install that cannot be wrong about itself must not be told it is broken.
 * That is why `selfId` is compared before the registry is consulted at all.
 */
export function bindingState(
  boundId: string | null,
  { selfId, known }: BindingInput,
): BindingState {
  if (boundId === null) return "unbound";
  if (boundId === selfId) return "self";
  // An EMPTY registry can never be the fault, and the reason is what "unknown"
  // claims. A registry that holds machines and not this id has SHOWN that
  // nobody claims it. An empty one has shown nothing — there is none until a
  // remote is configured, and none for a moment after the working tree is
  // rebuilt. Reporting "no machine claims this" from "we cannot say" is
  // overclaiming, and it overclaims the one state that is a fault.
  //
  // Same rule, statement for statement, as
  // `GlobalInternalEngineConfig.curation_owner` in the backend domain. Two
  // facts of one shape resolving by two rules would leave a reader working out
  // which surface to believe.
  if (known.length === 0) return "other";
  return known.includes(boundId) ? "other" : "unknown";
}

/**
 * What a picker may bind to.
 *
 * This machine is ALWAYS offered, even when the registry is empty: a
 * single-machine install has never converged and so has no registry at all,
 * and it must still be able to name itself — the one install where an empty
 * pick-list would be fatal.
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

/** The option for one stored id, resolved the same way a picker would resolve
 *  it — so a surface that only REPORTS a binding and a surface that CHANGES
 *  one can never disagree about which machine an id is. */
export function machineOptionFor(
  machines: readonly Machine[],
  selfId: string | null,
  boundId: string,
): MachineOption {
  const options = machineOptions(machines, selfId, boundId);
  // machineOptions appends `boundId` when nothing claims it, so this never
  // falls through; the fallback is here only to keep the return type honest.
  return (
    options.find((o) => o.id === boundId) ?? {
      id: boundId,
      name: "",
      isSelf: false,
      known: false,
    }
  );
}
