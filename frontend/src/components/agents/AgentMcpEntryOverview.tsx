// frontend/src/components/agents/AgentMcpEntryOverview.tsx
// The body of a direct MCP server's detail page (spec agent-registry "Show one
// direct MCP entry's full configuration without its secrets"): the entry
// exactly as the agent's own config file holds it — one pretty-printed JSON
// object, read-only, with a Copy button — under a one-line caption naming the
// file and source it came from.
//
// The daemon sends the entry whole but already masked: every env / header
// value, and any value that looks like a credential (a secret-looking key, a
// `--token=…` argument, a URL's password), arrives as a mask. This component
// prints what it is given.
import { useEffect, useState } from "react";
import { Check, Copy } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Section } from "@/components/Section";
import { Card, CardContent } from "@/components/ui/card";
import type { McpEntryDetailOut } from "@/lib/api/agents-workspace";
import { abbreviateHomePath } from "@/lib/agents/display";

/** The entry's JSON, the file it sits in and the source naming it — an agent's
 *  direct entry, or a server a plugin bundles. */
export type McpEntryView = Pick<McpEntryDetailOut, "config" | "path" | "source">;

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
    <Card className="paper-card">
      <CardContent className="pt-5">
        <Section
          title={t("mcp.server.overview.config")}
          actions={
            <Button size="sm" variant="outline" onClick={copy}>
              {copied ? <Check aria-hidden /> : <Copy aria-hidden />}{" "}
              {copied ? t("common.copied") : t("agents.workspace.mcp.detail.copy")}
            </Button>
          }
        >
          <p className="break-all font-mono text-xs text-muted-foreground">
            {t("agents.workspace.mcp.detail.origin", {
              file: abbreviateHomePath(entry.path),
              source: entry.source,
            })}
          </p>
          <pre
            aria-label={t("mcp.server.overview.config")}
            className="max-h-[32rem] overflow-auto whitespace-pre-wrap break-all rounded-md border border-border-subtle bg-surface-sunken p-3 font-mono text-xs"
          >
            {json}
          </pre>
        </Section>
      </CardContent>
    </Card>
  );
}
