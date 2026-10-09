// src/components/mcp/server/McpResourceDetail.tsx — one resource opened in the Resources tab, one column like a tool's: what it is, its type, the address agents read it by, and its content read on demand (design 4.1.11).
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import type { components } from "@/lib/api/types";
import { useReadMcpResource } from "@/lib/hooks/useMcpCapabilityPreview";
import { McpPreviewResult } from "./McpPreviewResult";

type ResourceView = components["schemas"]["MCPResourceView"];

interface Props {
  serverUid: string;
  resource: ResourceView;
}

export function McpResourceDetail({ serverUid, resource }: Props) {
  const { t } = useTranslation();
  const read = useReadMcpResource(serverUid);
  const facts = [
    resource.name ? [t("mcp.page.preview.name"), resource.name] : null,
    [t("mcp.page.preview.mimeType"), resource.mime_type ?? "—"],
  ].filter((f): f is [string, string] => f !== null);
  return (
    <div
      className="mb-2 ml-12 mr-2 flex flex-col gap-2 rounded-lg bg-surface-sunken px-3 py-2.5 text-xs"
      data-testid="mcp-resource-detail"
    >
      {resource.description ? <p className="text-text">{resource.description}</p> : null}
      <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1">
        {facts.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-text-muted">{label}</dt>
            <dd className="min-w-0 break-all text-text">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="text-text-muted">
        {t("mcp.page.seenAs")}{" "}
        <code className="break-all font-mono text-text">{resource.prefixed_uri}</code>
      </p>
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-2">
          <span className="font-label text-text-muted">{t("mcp.page.preview.content")}</span>
          <Button
            size="sm"
            variant="secondary"
            disabled={read.isPending}
            onClick={() => read.mutate(resource.original_uri)}
          >
            {read.isPending
              ? t("mcp.page.preview.reading")
              : read.data || read.error
                ? t("mcp.page.preview.readAgain")
                : t("mcp.page.preview.read")}
          </Button>
        </div>
        <McpPreviewResult result={read.data} error={read.error} />
      </div>
    </div>
  );
}
