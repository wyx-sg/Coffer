// src/components/agents/mcp/McpParseErrorAlert.tsx — one agent config file that failed to parse, as an inline warning above the list.
//
// Board 2.1.30: the file's entries stay listed but read-only until it parses
// again, and the way to fix it is the person's own editor, which Open in editor
// opens on that file.
import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { McpEntriesResponse } from "@/lib/api/agents-workspace";
import { useFileActionItems } from "@/lib/fileActionItems";

type ParseError = McpEntriesResponse["parse_errors"][number];

export function McpParseErrorAlert({ error }: { error: ParseError }) {
  const { t } = useTranslation();
  const [open] = useFileActionItems(error.path);
  return (
    <div role="alert" className="flex items-start gap-2 text-sm text-warning">
      <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
      <p className="min-w-0 flex-1 text-text">
        {t("agents.mcpTab.parseError", {
          file: abbreviateHomePath(error.path),
          error: error.error.replace(/\.$/, ""),
        })}
      </p>
      <Button variant="ghost" size="sm" onClick={open.onClick}>
        {open.label}
      </Button>
    </div>
  );
}
