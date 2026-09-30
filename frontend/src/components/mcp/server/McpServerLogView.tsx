// src/components/mcp/server/McpServerLogView.tsx — the drawer's Server log tab (design 4.1.10).
//
// What the server printed on stderr and how Coffer started and stopped it,
// newest first; Everything or only the error lines; Copy what is shown, and
// Open log file. A server Coffer does not start (Streamable HTTP) has no log,
// and the tab says so.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy, FileText } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { fsApi } from "@/lib/api/fs";
import { translateApiError } from "@/lib/api/errors";
import { useMcpServerLog } from "@/lib/hooks/useMcpServerPage";
import { cn } from "@/lib/utils";
import { shortTime } from "./serverState";

const ERROR_LINE = /\b(error|failed|exception|traceback|not found|refused|denied)\b/i;

interface Props {
  serverUid: string;
  isHttp: boolean;
}

export function McpServerLogView({ serverUid, isHttp }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const log = useMcpServerLog(serverUid, !isHttp);
  const [only, setOnly] = useState<"all" | "errors">("all");

  if (isHttp) return <p className="text-xs text-text-muted">{t("mcp.page.log.noLogHttp")}</p>;
  if (log.isPending) return <Skeleton className="h-40 w-full" />;
  if (log.error) return <p className="text-xs text-danger">{translateApiError(t, log.error)}</p>;

  const lines = (log.data?.lines ?? []).filter((l) => only === "all" || ERROR_LINE.test(l.text));
  const path = log.data?.path ?? null;
  const text = lines
    .map((l) => [l.at ? shortTime(l.at) : "", l.source, l.text].filter(Boolean).join(" "))
    .join("\n");
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success(t("common.copied"));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Segmented
          label={t("mcp.page.log.show")}
          value={only}
          onChange={setOnly}
          options={[
            { value: "all", label: t("mcp.page.log.everything") },
            { value: "errors", label: t("mcp.page.log.errorLines") },
          ]}
        />
        <span className="ml-auto inline-flex gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={lines.length === 0}
            onClick={() => void copy()}
          >
            <Copy aria-hidden /> {t("common.copy")}
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={!path}
            onClick={() =>
              path &&
              fsApi.open(path).catch((err: unknown) => toast.error(translateApiError(t, err)))
            }
          >
            <FileText aria-hidden /> {t("mcp.page.log.openFile")}
          </Button>
        </span>
      </div>
      {lines.length === 0 ? (
        <p className="text-xs text-text-muted">
          {path ? t("mcp.page.log.nothing") : t("mcp.page.log.notStarted")}
        </p>
      ) : (
        <pre
          className="min-h-0 flex-1 overflow-auto rounded-md border border-border-subtle bg-surface-sunken p-3 font-mono text-2xs leading-relaxed"
          data-testid="mcp-server-log"
        >
          {lines.map((l, i) => (
            <div key={i} className="flex gap-3">
              <span className="w-24 shrink-0 text-text-subtle">{l.at ? shortTime(l.at) : ""}</span>
              <span
                className={cn(
                  "w-12 shrink-0",
                  l.source === "coffer" ? "text-accent" : "text-text-muted",
                )}
              >
                {l.source}
              </span>
              <span className="min-w-0 whitespace-pre-wrap break-all text-text">{l.text}</span>
            </div>
          ))}
        </pre>
      )}
      <p className="text-xs text-text-muted">{t("mcp.page.log.logFootnote")}</p>
    </div>
  );
}
