// src/components/custom-tools/ToolTestResult.tsx — what one test run got: the status line (or how it
// failed), the URL it called, the body, and a line on what to do next.
import { useTranslation } from "react-i18next";
import { TriangleAlert } from "lucide-react";

import { StatusWord } from "@/components/status/StatusWord";
import type { CustomToolTestOut } from "@/lib/api/customTools";
import { hostOf } from "@/lib/customTools/groups";
import { formatBytes } from "@/lib/utils";

/** The most of a response a tool returns (mcp-gateway "Make a custom tool's
 *  request in the gateway": at most 1 MiB is read). */
export const RESPONSE_CAP_BYTES = 1024 * 1024;

interface Props {
  result: CustomToolTestOut;
  method: string;
  /** The group's name and secret, for the rejected-secret hint. */
  group: string;
  secret: string | null;
  timeoutSeconds: number;
}

function kindOf(contentType: string | null): string {
  if (!contentType) return "";
  if (contentType.includes("json")) return "JSON";
  if (contentType.includes("html")) return "HTML";
  if (contentType.includes("xml")) return "XML";
  return contentType.split(";")[0];
}

export function ToolTestResult({ result, method, group, secret, timeoutSeconds }: Props) {
  const { t } = useTranslation();
  const host = result.url ? hostOf(result.url) : "";
  const status = (result.status_line ?? "").replace(/^HTTP /, "");
  const rejected = result.status === 401 || result.status === 403;

  const title = result.failure
    ? t(`customTools.test.failure.${result.failure}`, { host, seconds: timeoutSeconds })
    : t("customTools.test.summary", {
        status,
        ms: result.duration_ms,
        size: formatBytes(new TextEncoder().encode(result.body).length),
        kind: kindOf(result.content_type),
      });
  const hint = result.failure
    ? t(`customTools.test.hint.${result.failure}`, {
        host,
        seconds: timeoutSeconds,
        reason: result.error ?? "",
      })
    : rejected && secret
      ? t("customTools.test.hint.rejected", { secret, group })
      : !result.ok
        ? t("customTools.test.hint.httpError")
        : null;

  return (
    <div
      className="flex flex-col gap-2 rounded-lg border border-border-subtle p-3"
      data-testid="custom-tool-test-result"
    >
      <StatusWord tone={result.ok ? "ok" : "err"}>{title}</StatusWord>
      {result.url ? (
        <p className="flex min-w-0 items-center gap-2">
          <span className="shrink-0 rounded-sm bg-chip px-1.5 font-mono text-2xs text-text-muted">
            {method}
          </span>
          <span className="truncate font-mono text-xs text-text-muted" title={result.url}>
            {result.url}
          </span>
        </p>
      ) : null}
      {result.body ? (
        <pre className="max-h-64 overflow-auto rounded-lg bg-code p-3 font-mono text-xs">
          {result.body}
        </pre>
      ) : null}
      {hint ? <p className="text-xs text-text-muted">{hint}</p> : null}
      {result.truncated ? (
        <div className="flex items-start gap-2 rounded-lg bg-warning-soft px-3 py-2 text-xs">
          <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-warning" aria-hidden />
          <span>
            <span className="font-label text-text">
              {t("customTools.test.cutShort", { size: formatBytes(RESPONSE_CAP_BYTES) })}
            </span>{" "}
            <span className="text-text-muted">
              {t("customTools.test.cutShortBody", { size: formatBytes(RESPONSE_CAP_BYTES) })}
            </span>
          </span>
        </div>
      ) : null}
    </div>
  );
}
