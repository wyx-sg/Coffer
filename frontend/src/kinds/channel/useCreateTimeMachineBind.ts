// frontend/src/kinds/channel/useCreateTimeMachineBind.ts
//
// Create-time auto-bind (spec 010 affinity, ADR-045): the creating machine
// claims a freshly-registered channel so its adapter starts right away.
// Routed through the scope API (not config.runs_on, now inert) — same PUT
// .../scope call ChannelMachineCard's "run here" button makes. Extracted
// from AddChannelDialog.tsx to keep that file under the component size
// limit.
import { useSyncMachines } from "@/lib/hooks/useSync";
import { useUpdateChannelScope } from "@/lib/hooks/useChannels";

export function useCreateTimeMachineBind(pendingName: string) {
  const { data: machines } = useSyncMachines();
  const bindScope = useUpdateChannelScope(pendingName);

  // Best-effort: a failure here surfaces its own toast (useUpdateChannelScope's
  // onError) but must not undo the already-created channel — the user can
  // still bind it manually from the channel's detail page.
  const bindToLocalMachine = () => {
    const localMachine = machines?.machines.find((m) => m.is_local)?.machine_id;
    if (localMachine) {
      bindScope.mutate({ [localMachine]: "*" });
    }
  };

  return { machines, bindToLocalMachine };
}
