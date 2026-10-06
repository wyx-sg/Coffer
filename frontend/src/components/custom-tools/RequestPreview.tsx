// src/components/custom-tools/RequestPreview.tsx — what Run would send from a saved group's tool form, in the one
// environment the form has chosen: method and URL, the merged headers (a secret header by its secret's name and
// state, never a value), the environment's variables and the timeout that applies. Built by the daemon's rules
// (lib/customTools/environmentContext.ts); `{argument}` holes stay until the request runs.
import { useTranslation } from "react-i18next";

import type { CustomToolEnvironment, CustomToolGroup } from "@/lib/api/customTools";
import { effectiveTimeout, requestPreview } from "@/lib/customTools/environmentContext";
import { cn } from "@/lib/utils";
import { AuthLine } from "./AuthLine";

interface Props {
  group: CustomToolGroup;
  environment: CustomToolEnvironment;
  method: string;
  tool: { path: string; headers?: Record<string, string> | null };
}

export function RequestPreview({ group, environment, method, tool }: Props) {
  const { t } = useTranslation();
  const preview = requestPreview(environment, tool);
  const timeout = effectiveTimeout(group, environment);
  const variables = Object.entries(environment.variables ?? {});
  return (
    <div
      role="group"
      aria-label={t("customTools.preview.title", { environment: environment.name })}
      data-testid="custom-tool-request-preview"
      className="flex flex-col gap-1 rounded-lg border border-border-subtle bg-surface-sunken px-3 py-2"
    >
      <p className="flex min-w-0 items-center gap-2">
        <span className="shrink-0 rounded-sm bg-chip px-1.5 font-mono text-2xs text-text-muted">
          {method}
        </span>
        <span className="min-w-0 break-all font-mono text-xs text-text" title={preview.url}>
          {preview.url}
        </span>
      </p>
      {preview.headers.map((h) =>
        h.secret?.secret ? (
          <AuthLine
            key={h.name}
            header={h.name}
            secret={h.secret.secret}
            plain
            trailing={
              <span
                className={cn(
                  "text-xs",
                  h.secret.secret_state === "present" ? "text-text-muted" : "text-warning",
                )}
              >
                {t(`customTools.preview.secretState.${h.secret.secret_state}`)}
              </span>
            }
          />
        ) : (
          <p key={h.name} className="break-all font-mono text-xs text-text-muted">
            {h.name}: {h.value}
          </p>
        ),
      )}
      {variables.length > 0 ? (
        <p className="break-all text-xs text-text-muted">
          {t("customTools.preview.variables")}{" "}
          <span className="font-mono">{variables.map(([k, v]) => `${k}=${v}`).join(" · ")}</span>
        </p>
      ) : null}
      {preview.missingVariables.length > 0 ? (
        <p role="alert" className="text-xs text-danger">
          {t("customTools.preview.missingVariables", {
            names: preview.missingVariables.map((n) => `{env:${n}}`).join(", "),
            environment: environment.name,
          })}
        </p>
      ) : null}
      <p className="text-xs text-text-muted">
        {t(`customTools.preview.timeout.${timeout.source}`, {
          seconds: timeout.seconds,
          environment: environment.name,
        })}
      </p>
    </div>
  );
}
