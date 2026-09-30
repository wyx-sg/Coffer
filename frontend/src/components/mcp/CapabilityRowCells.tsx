// frontend/src/components/mcp/CapabilityRowCells.tsx — a capability row's enable switch, shared by the tool, resource and prompt tables.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Switch } from "@/components/ui/switch";
import { useDisableCapability, useEnableCapability } from "@/lib/hooks/useMcpCapabilityMutations";
import type { CapabilityKind, RowDescriptor } from "./capabilityRows";

export function ToggleSwitch({
  serverUid,
  kind,
  row,
}: {
  serverUid: string;
  kind: CapabilityKind;
  row: RowDescriptor;
}) {
  const { t } = useTranslation();
  const enable = useEnableCapability();
  const disable = useDisableCapability();
  // Per-row in-flight state: this switch is the only one toggling, so a single
  // boolean suffices (the per-row scope is naturally enforced by component
  // instance rather than a shared key set).
  const [pending, setPending] = useState(false);

  return (
    <Switch
      checked={row.enabled}
      disabled={pending}
      aria-label={t("mcp.capabilities.toggleAria", { kind, key: row.key })}
      onClick={(e) => e.stopPropagation()}
      onCheckedChange={(checked) => {
        const m = checked ? enable : disable;
        setPending(true);
        m.mutate(
          {
            serverUid,
            capabilityType: kind,
            capabilityKey: row.key,
          },
          { onSettled: () => setPending(false) },
        );
      }}
    />
  );
}
