// src/components/mcp/server/McpToolExposure.tsx — one tool's exposure control: Auto · Listed, Always listed or Search only (spec mcp-gateway "Choose how each tool is exposed").
//
// The trigger reads the setting, and for Auto what the usage ranking gave the
// tool right now ("Auto · Listed"); the reason is on the row's detail.
import { useTranslation } from "react-i18next";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { ToolExposure, ToolExposureMode } from "@/lib/api/mcpServers";
import { useExposureLabel } from "./exposureLabel";
import { useSetToolExposure } from "@/lib/hooks/useMcpToolExposure";

const MODES: readonly ToolExposureMode[] = ["auto", "listed", "search"];

interface Props {
  serverUid: string;
  tool: string;
  exposure: ToolExposure;
}

export function McpToolExposure({ serverUid, tool, exposure }: Props) {
  const { t } = useTranslation();
  const label = useExposureLabel();
  const set = useSetToolExposure();
  return (
    <Select
      value={exposure.mode}
      disabled={set.isPending}
      onValueChange={(mode) =>
        set.mutate({ serverUid, tools: [tool], mode: mode as ToolExposureMode })
      }
    >
      <SelectTrigger
        aria-label={t("mcp.exposure.aria", { key: tool })}
        className="h-7 w-full text-xs"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.stopPropagation()}
      >
        <SelectValue>{label(exposure)}</SelectValue>
      </SelectTrigger>
      <SelectContent>
        {MODES.map((mode) => (
          <SelectItem key={mode} value={mode}>
            {t(`mcp.exposure.mode.${mode}`)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
