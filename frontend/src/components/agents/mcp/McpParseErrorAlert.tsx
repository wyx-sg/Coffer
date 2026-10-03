// src/components/agents/mcp/McpParseErrorAlert.tsx — one agent config file that failed to parse, as an inline warning above the list.
//
// Board 2.1.30: the file's entries stay listed but read-only until it parses
// again, and the way to fix it is the Config files tab, which opens on that file.
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { abbreviateHomePath } from "@/lib/agents/display";
import { agentTabPath } from "@/lib/agents/routes";
import type { McpEntriesResponse } from "@/lib/api/agents-workspace";

type ParseError = McpEntriesResponse["parse_errors"][number];

export function McpParseErrorAlert({ agentType, error }: { agentType: string; error: ParseError }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  return (
    <div role="alert" className="flex items-start gap-2 text-sm text-warning">
      <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
      <p className="min-w-0 flex-1 text-text">
        {t("agents.mcpTab.parseError", {
          file: abbreviateHomePath(error.path),
          error: error.error.replace(/\.$/, ""),
        })}
      </p>
      <Button
        variant="ghost"
        size="sm"
        // The entry's `source` is the file's config-file key, which is what the
        // Config files tab selects by (`?file=<key>`).
        onClick={() =>
          navigate(
            `${agentTabPath(agentType, "config")}?${new URLSearchParams({ file: error.source })}`,
          )
        }
      >
        {t("agents.mcpTab.openConfigFiles")}
      </Button>
    </div>
  );
}
