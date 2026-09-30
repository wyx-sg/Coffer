// src/components/agents/mcp/McpParseErrorAlert.tsx — one agent config file that failed to parse, shown above the MCP table.
//
// Board 2.1.27: the file's entries stay listed but read-only until it parses
// again, and the way to fix it is the Config files tab.
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { AlertTriangle, FileCode } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { abbreviateHomePath } from "@/lib/agents/display";
import { agentTabPath } from "@/lib/agents/routes";
import type { McpEntriesResponse } from "@/lib/api/agents";

type ParseError = McpEntriesResponse["parse_errors"][number];

export function McpParseErrorAlert({ agentType, error }: { agentType: string; error: ParseError }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  return (
    <Alert variant="warning">
      <AlertTriangle aria-hidden />
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <AlertTitle>
            {t("agents.mcpTab.parseErrorTitle", { file: abbreviateHomePath(error.path) })}
          </AlertTitle>
          <AlertDescription>
            {t("agents.mcpTab.parseErrorBody", { error: error.error.replace(/\.$/, "") })}
          </AlertDescription>
        </div>
        <Button
          variant="outline"
          size="sm"
          // The entry's `source` is the file's config-file key, which is what the
          // Config files tab selects by (`?file=<key>`).
          onClick={() =>
            navigate(
              `${agentTabPath(agentType, "config")}?${new URLSearchParams({ file: error.source })}`,
            )
          }
        >
          <FileCode aria-hidden />
          {t("agents.mcpTab.openConfigFiles")}
        </Button>
      </div>
    </Alert>
  );
}
