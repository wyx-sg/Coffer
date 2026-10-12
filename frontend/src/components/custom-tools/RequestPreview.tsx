// src/components/custom-tools/RequestPreview.tsx — the Test tab's "Request to send": what one run sends with the
// sample values typed so far (lib/customTools/sentRequest.ts), in the environment the tab names — the method and the
// full URL, the merged headers in the shared table (a secret header by its secret's name and state, never a value),
// the body laid out as JSON, then the environment's variables and the timeout that applies.
import { useTranslation } from "react-i18next";

import { CodeView } from "@/components/preview/CodeView";
import type { SentRequest } from "@/lib/customTools/sentRequest";
import { CopyUrlLine } from "./CopyUrlLine";
import { HeaderTable } from "./HeaderTable";

interface Props {
  method: string;
  sent: SentRequest;
  /** The environment it runs in; null before the group exists. */
  environment: string | null;
  variables: Record<string, string>;
  missingVariables: string[];
  /** "Timeout 30 s (the group's)". */
  timeoutLine: string;
}

export function RequestPreview({
  method,
  sent,
  environment,
  variables,
  missingVariables,
  timeoutLine,
}: Props) {
  const { t } = useTranslation();
  const vars = Object.entries(variables);
  return (
    <section
      aria-label={t("customTools.test.requestTitle")}
      data-testid="custom-tool-request-preview"
      className="flex flex-col gap-3"
    >
      <h3 className="flex items-baseline gap-2 text-sm font-label">
        {t("customTools.test.requestTitle")}
        {environment ? (
          <span className="text-xs font-normal text-text-muted">
            {t("customTools.test.inEnvironment", { environment })}
          </span>
        ) : null}
      </h3>
      <div className="rounded-lg border border-border-subtle bg-surface-sunken px-3 py-2">
        <CopyUrlLine method={method} url={sent.url} wrap />
      </div>
      {sent.missingPath.length > 0 ? (
        <p role="alert" className="text-xs text-warning">
          {t("customTools.test.missingPath", {
            names: sent.missingPath.map((n) => `{${n}}`).join(", "),
          })}
        </p>
      ) : null}
      <HeaderTable
        ariaLabel={t("customTools.editor.headers")}
        sources
        empty={t("customTools.editor.noHeaders")}
        rows={sent.headers.map((h) => ({
          name: h.name,
          value: h.value,
          secret: h.secret?.secret ?? null,
          secretState: h.secret?.secret_state ?? null,
          source:
            h.from === "environment"
              ? environment
                ? t("customTools.editor.fromEnvironment", { environment })
                : t("customTools.editor.fromGroup")
              : t("customTools.editor.fromTool"),
        }))}
      />
      {sent.body !== null ? (
        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-label text-text-muted">
            {t("customTools.test.bodyLabel")}
          </span>
          <CodeView
            value={sent.body}
            language="json"
            maxHeight="20rem"
            wrap
            ariaLabel={t("customTools.test.bodyLabel")}
          />
        </div>
      ) : null}
      {vars.length > 0 ? (
        <p className="break-all text-xs text-text-muted">
          {t("customTools.preview.variables")}{" "}
          <span className="font-mono">{vars.map(([k, v]) => `${k}=${v}`).join(" · ")}</span>
        </p>
      ) : null}
      {missingVariables.length > 0 && environment ? (
        <p role="alert" className="text-xs text-danger">
          {t("customTools.preview.missingVariables", {
            names: missingVariables.map((n) => `{env:${n}}`).join(", "),
            environment,
          })}
        </p>
      ) : null}
      <p className="text-xs text-text-muted">{timeoutLine}</p>
    </section>
  );
}
