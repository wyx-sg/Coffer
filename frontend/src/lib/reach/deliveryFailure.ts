// frontend/src/lib/reach/deliveryFailure.ts
//
// A reach write can land (the scope is saved) and still fail to deliver to one
// agent — a skill's link into ~/.codex/skills was refused. The scope write's
// answer carries a per-agent `delivery` list for that (canvas 4.3.09); this
// turns the first failed entry into an Error the reach popovers show on that
// agent's row (single) or in the error block (bulk), never as a toast.
import { scopeApi, type Scope } from "@/lib/api/scope";

/** The write was saved, but delivering it to `agentUid` failed. The message is the reason. */
export class DeliveryError extends Error {
  readonly agentUid: string;
  constructor(agentUid: string, reason: string) {
    super(reason);
    this.name = "DeliveryError";
    this.agentUid = agentUid;
  }
}

/** PUT the scope; throws a DeliveryError when the saved scope could not reach an agent. */
export async function putScopeChecked(uid: string, scope: Scope | null): Promise<void> {
  const saved = await scopeApi.put(uid, scope);
  const bad = saved?.delivery?.find((d) => !d.ok);
  if (bad) throw new DeliveryError(bad.agent_uid, bad.reason ?? bad.agent_name);
}
