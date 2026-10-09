// src/components/custom-tools/ToolTestResult.tsx — what one test run got (4.2.08–4.2.12), under the form's fields:
//  · an answer: a neutral sunken block — green ✓, grey status line, the URL — the response in the viewer below it;
//  · the API's error (4xx/5xx): a danger-soft block, no hand-off (401/403 add Change value for the secret);
//  · no connection / timeout: a danger-soft block with Hand off to <Agent> ▾ and ? (a timeout also Change timeout).
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, CircleAlert, Copy } from "lucide-react";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { ReplaceSecretDialog } from "@/components/secret/ReplaceSecretDialog";
import { useSecretChoices } from "@/components/secret/useSecretChoices";
import { Button } from "@/components/ui/button";
import type { CustomToolTestOut } from "@/lib/api/customTools";
import { hostOf } from "@/lib/customTools/groups";
import { cn, formatBytes } from "@/lib/utils";
import { ResponseViewer } from "./ResponseViewer";

/** The most of a response a tool returns (mcp-gateway "Make a custom tool's
 *  request in the gateway": at most 1 MiB is read). */
const RESPONSE_CAP_BYTES = 1024 * 1024;

interface Props {
  result: CustomToolTestOut;
  method: string;
  /** The group's name and the secret its headers read, for the rejected-secret hint. */
  group: string;
  secret: string | null;
  timeoutSeconds: number;
  /** The environment whose own timeout applied; null when it was the group's. */
  timeoutEnvironment?: string | null;
  /** A timeout offers "Change timeout" (opens Edit group); omit before the group exists. */
  onChangeTimeout?: () => void;
}

function kindOf(contentType: string | null): string {
  if (!contentType) return "";
  if (contentType.includes("json")) return "JSON";
  if (contentType.includes("html")) return "HTML";
  if (contentType.includes("xml")) return "XML";
  return contentType.split(";")[0];
}

function took(ms: number): string {
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

function UrlLine({ method, url }: { method: string; url: string }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  return (
    <p className="flex min-w-0 items-center gap-2">
      <span className="shrink-0 rounded-sm bg-chip px-1.5 font-mono text-2xs text-text-muted">
        {method}
      </span>
      <span className="min-w-0 truncate font-mono text-xs text-text-muted" title={url}>
        {url}
      </span>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        aria-label={t("common.copy")}
        className="text-text-subtle"
        onClick={() =>
          void navigator.clipboard?.writeText(url).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          })
        }
      >
        {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
      </Button>
    </p>
  );
}

/** The allow-listed response headers the daemon kept (request and trace ids, server, date). */
function ResponseHeaders({ headers }: { headers: Record<string, string> }) {
  const { t } = useTranslation();
  const rows = Object.entries(headers);
  if (rows.length === 0) return null;
  return (
    <div aria-label={t("customTools.test.responseHeaders")} className="flex flex-col gap-0.5">
      {rows.map(([name, value]) => (
        <p key={name} className="break-all font-mono text-2xs text-text-muted">
          {name}: {value}
        </p>
      ))}
    </div>
  );
}

export function ToolTestResult({
  result,
  method,
  group,
  secret,
  timeoutSeconds,
  timeoutEnvironment = null,
  onChangeTimeout,
}: Props) {
  const { t } = useTranslation();
  const { rowOf, displayOf } = useSecretChoices();
  const [changing, setChanging] = useState(false);
  const host = result.url ? hostOf(result.url) : "";
  const status = (result.status_line ?? "").replace(/^HTTP /, "");
  const rejected = (result.status === 401 || result.status === 403) && secret !== null;
  const failed = result.failure !== null;
  const good = result.ok && !failed;
  const size = formatBytes(new TextEncoder().encode(result.body).length);

  const title = failed
    ? t(`customTools.test.failure.${result.failure}`, { host, seconds: timeoutSeconds })
    : t(result.truncated ? "customTools.test.summaryCut" : "customTools.test.summary", {
        status,
        duration: took(result.duration_ms),
        size,
        kind: kindOf(result.content_type),
      });
  const hint = failed
    ? t(
        result.failure === "timeout" && timeoutEnvironment
          ? "customTools.test.hint.timeoutEnv"
          : `customTools.test.hint.${result.failure}`,
        {
          host,
          group,
          environment: timeoutEnvironment,
          seconds: timeoutSeconds,
          reason: result.error ?? "",
          detail: result.error ? ` (${result.error})` : "",
        },
      )
    : rejected
      ? result.environment
        ? t("customTools.test.hint.rejectedEnv", {
            secret: displayOf(secret),
            environment: result.environment,
          })
        : t("customTools.test.hint.rejected", { secret: displayOf(secret), group })
      : !result.ok
        ? t("customTools.test.hint.httpError")
        : null;
  // The daemon sends the prompt for a failure that depends on this machine (no connection, timeout).
  const handoff = result.handoff?.prompt ?? null;
  const actions =
    (result.failure === "timeout" && onChangeTimeout) || rejected || handoff ? (
      <div className="flex flex-wrap items-center gap-2">
        {result.failure === "timeout" && onChangeTimeout ? (
          <Button type="button" size="sm" variant="outline" onClick={onChangeTimeout}>
            {t("customTools.test.changeTimeout")}
          </Button>
        ) : null}
        {rejected ? (
          <Button type="button" size="sm" variant="outline" onClick={() => setChanging(true)}>
            {t("customTools.test.changeValue")}
          </Button>
        ) : null}
        {handoff ? <AgentHandoff prompt={handoff} size="sm" /> : null}
      </div>
    ) : null;

  return (
    <div className="flex flex-col gap-2">
      <div
        role={good ? "status" : "alert"}
        data-testid="custom-tool-test-result"
        className={cn(
          "flex flex-col gap-2 rounded-lg p-3",
          good ? "border border-border-subtle bg-surface-sunken" : "bg-danger-soft",
        )}
      >
        <p
          className={cn(
            "flex items-center gap-2 text-sm font-label",
            good ? "text-text-muted" : "text-text",
          )}
        >
          {good ? (
            <Check className="size-[15px] shrink-0 text-success" aria-hidden />
          ) : (
            <CircleAlert className="size-[15px] shrink-0 text-danger" aria-hidden />
          )}
          {title}
        </p>
        {result.environment ? (
          <p className="text-xs text-text-muted">
            {t("customTools.test.ranIn", { environment: result.environment })}
          </p>
        ) : null}
        {result.url ? <UrlLine method={method} url={result.url} /> : null}
        <ResponseHeaders headers={result.response_headers ?? {}} />
        {hint ? <p className="text-xs leading-[1.45] text-text-muted">{hint}</p> : null}
        {actions}
      </div>
      {result.body ? (
        <ResponseViewer
          body={result.body}
          contentType={result.content_type}
          cutAt={result.truncated ? formatBytes(RESPONSE_CAP_BYTES) : null}
        />
      ) : null}
      <ReplaceSecretDialog
        row={changing && secret ? (rowOf(secret) ?? null) : null}
        onOpenChange={setChanging}
      />
    </div>
  );
}
