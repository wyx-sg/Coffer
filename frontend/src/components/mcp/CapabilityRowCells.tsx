// frontend/src/components/mcp/CapabilityRowCells.tsx — the per-row pieces of
// CapabilityList: the over-long client-name flag and the enable switch.
//
// Split out of CapabilityList.tsx to keep that file within its size budget.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Switch } from "@/components/ui/switch";
import { toneClass } from "@/lib/statusColors";
import { cn } from "@/lib/utils";
import { useDisableCapability, useEnableCapability } from "@/lib/hooks/useMcpCapabilityMutations";
import { CLIENT_NAME_LIMIT, type CapabilityKind, type RowDescriptor } from "./capabilityRows";

export function ClientNameFlag({ length }: { length: number }) {
  const { t } = useTranslation();
  return (
    <p className={cn("mt-1 w-fit rounded-sm px-1.5 py-0.5 text-xs", toneClass("warn"))} role="note">
      {t("mcp.capabilities.nameTooLong", { length, limit: CLIENT_NAME_LIMIT })}
    </p>
  );
}

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
