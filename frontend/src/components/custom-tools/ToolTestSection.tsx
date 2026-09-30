// src/components/custom-tools/ToolTestSection.tsx — Test: sample argument values, one run of the draft as
// it stands (nothing is saved), and the response it got.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Play } from "lucide-react";

import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { translateApiError } from "@/lib/api/errors";
import type { CustomToolIn } from "@/lib/api/customTools";
import { testArguments, type ArgRow } from "@/lib/customTools/schemaArgs";
import { useTestCustomTool } from "@/lib/hooks/useCustomTools";
import { formatBytes } from "@/lib/utils";

interface Props {
  group: string;
  secret: string | null;
  args: ArgRow[];
  /** The draft as the form holds it now. */
  draft: () => CustomToolIn;
  ready: boolean;
}

function kindOf(contentType: string | null): string {
  if (!contentType) return "";
  if (contentType.includes("json")) return "JSON";
  if (contentType.includes("html")) return "HTML";
  if (contentType.includes("xml")) return "XML";
  return contentType.split(";")[0];
}

export function ToolTestSection({ group, secret, args, draft, ready }: Props) {
  const { t } = useTranslation();
  const test = useTestCustomTool(group);
  const [values, setValues] = useState<Record<string, string>>({});
  const result = test.data;
  const named = args.filter((row) => row.name);
  const run = () => test.mutate({ tool: draft(), args: testArguments(args, values) });

  return (
    <section aria-labelledby="ct-test" className="flex flex-col gap-2">
      <h3 id="ct-test" className="text-sm font-semibold">
        {t("customTools.test.title")}
      </h3>
      {named.length > 0 ? (
        <div className="grid grid-cols-2 gap-2">
          {named.map((row) => (
            <Input
              key={row.name}
              className="font-mono"
              placeholder={row.name}
              aria-label={t("customTools.test.valueFor", { name: row.name })}
              value={values[row.name] ?? ""}
              onChange={(e) => setValues({ ...values, [row.name]: e.target.value })}
            />
          ))}
        </div>
      ) : null}
      <Button variant="outline" className="w-fit" disabled={!ready || test.isPending} onClick={run}>
        <Play aria-hidden />
        {test.isPending
          ? t("customTools.test.running")
          : result
            ? t("customTools.test.runAgain")
            : t("customTools.test.run")}
      </Button>
      {test.error ? (
        <p role="alert" className="text-xs text-danger">
          {translateApiError(t, test.error)}
        </p>
      ) : null}
      {result ? (
        <div className="space-y-1.5" data-testid="custom-tool-test-result">
          <StatusWord tone={result.ok ? "ok" : "err"}>
            {result.status_line
              ? t("customTools.test.summary", {
                  status: result.status_line,
                  ms: result.duration_ms,
                  size: formatBytes(new TextEncoder().encode(result.body).length),
                  kind: kindOf(result.content_type),
                })
              : (result.error ?? t("customTools.test.failed"))}
          </StatusWord>
          {result.url ? (
            <p className="truncate font-mono text-xs text-text-muted">
              {draft().method ?? "GET"} {result.url}
            </p>
          ) : null}
          {result.status_line && result.error ? (
            <p className="text-xs text-danger">{result.error}</p>
          ) : null}
          {result.body ? (
            <pre className="max-h-64 overflow-auto rounded-lg bg-code p-3 font-mono text-xs">
              {result.body}
            </pre>
          ) : null}
          {result.truncated ? (
            <p className="text-xs text-text-muted">{t("customTools.test.truncated")}</p>
          ) : null}
        </div>
      ) : null}
      <p className="text-xs text-text-muted">
        {secret ? t("customTools.test.noteSecret", { secret }) : t("customTools.test.note")}
      </p>
    </section>
  );
}
