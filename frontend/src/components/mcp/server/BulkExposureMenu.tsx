// src/components/mcp/server/BulkExposureMenu.tsx — the selection bar's Exposure ▾ menu (spec mcp-gateway "Choose how each tool is exposed").
//
// Auto · Always listed · Search only for the ticked tools; an MCP server's
// Tools tab and a custom tool group's tools share it. Only tools that are on
// have an exposure, so the caller passes those.
import { useTranslation } from "react-i18next";
import { ChevronDown } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ActionMenu } from "@/components/ui/menu";
import type { ToolExposureMode } from "@/lib/api/mcpServers";

const MODES: readonly ToolExposureMode[] = ["auto", "listed", "search"];

interface Props {
  disabled: boolean;
  onPick: (mode: ToolExposureMode) => void;
}

export function BulkExposureMenu({ disabled, onPick }: Props) {
  const { t } = useTranslation();
  return (
    <ActionMenu
      label={t("common.bulk.exposure")}
      align="start"
      trigger={
        <Button size="sm" variant="outline" aria-haspopup="menu" disabled={disabled}>
          {t("common.bulk.exposure")}
          <ChevronDown aria-hidden />
        </Button>
      }
      actions={MODES.map((mode) => ({
        key: mode,
        label: t(`mcp.exposure.mode.${mode}`),
        onSelect: () => onPick(mode),
      }))}
    />
  );
}
