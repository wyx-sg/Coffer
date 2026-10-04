// src/components/mcp/server/exposureLabel.ts — the words for a tool's exposure, shared by its control and its detail.
import { useTranslation } from "react-i18next";

import type { ToolExposure } from "@/lib/api/mcpServers";

/** The words for an exposure: "Auto · Listed", "Always listed", "Search only". */
export function useExposureLabel() {
  const { t } = useTranslation();
  return (e: Pick<ToolExposure, "mode" | "effective">) =>
    e.mode === "auto"
      ? t("mcp.exposure.autoNow", {
          now: e.effective === "listed" ? t("mcp.page.listed") : t("mcp.page.behindSearch"),
        })
      : t(`mcp.exposure.mode.${e.mode}`);
}
