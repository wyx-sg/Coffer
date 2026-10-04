// frontend/src/components/agents/AgentMcpEntryOverview.tsx
// The body of a direct MCP server's dialog (board 2.1.59, spec agent-registry
// "Show one direct MCP entry's full configuration without its secrets"): an
// origin line naming the file, a Copy JSON button, and the entry exactly as the
// agent's own config file holds it — one pretty-printed JSON object in the
// line-numbered read-only viewer.
//
// The daemon sends the entry whole but already masked: every env / header
// value, and any value that looks like a credential (a secret-looking key, a
// `--token=…` argument, a URL's password), arrives as a mask. This component
// prints what it is given.
import { useEffect, useState } from "react";
import { Check, Copy } from "lucide-react";
import { useTranslation } from "react-i18next";

import { CodeView } from "@/components/preview/CodeView";
import { Button } from "@/components/ui/button";
import type { McpEntryDetailOut } from "@/lib/api/agents-workspace";
import { abbreviateHomePath } from "@/lib/agents/display";

/** The entry's JSON and the file it sits in. */
export type McpEntryView = Pick<McpEntryDetailOut, "config" | "path">;

export function AgentMcpEntryOverview({ entry }: { entry: McpEntryView }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const json = JSON.stringify(entry.config, null, 2);

  useEffect(() => {
    if (!copied) return undefined;
    const timer = setTimeout(() => setCopied(false), 1500);
    return () => clearTimeout(timer);
  }, [copied]);

  const copy = () => {
    void navigator.clipboard?.writeText(json).then(() => setCopied(true));
  };

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex items-center gap-3">
        <p className="min-w-0 flex-1 break-all text-xs text-text-muted">
          {t("agents.mcpTab.entry.from")}{" "}
          <span className="font-mono text-text">{abbreviateHomePath(entry.path)}</span>
        </p>
        <Button size="sm" variant="outline" onClick={copy}>
          {copied ? <Check aria-hidden /> : <Copy aria-hidden />}{" "}
          {copied ? t("common.copied") : t("agents.mcpTab.entry.copy")}
        </Button>
      </div>
      <CodeView
        value={json}
        language="json"
        maxHeight="20rem"
        ariaLabel={t("mcp.server.overview.config")}
      />
    </div>
  );
}
