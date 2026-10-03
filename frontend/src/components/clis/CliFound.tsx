// src/components/clis/CliFound.tsx — what Coffer finds for the command typed in the Add CLI dialog, in a grey block under the field (boards 4.4.13–4.4.15).
//
// Found: where and which version (a green check). Not on this machine: a
// warning that it can still be added. Already added: a danger line. Already
// required by a skill or MCP server: an info line — adding it keeps it listed
// even when they stop requiring it.
import { Check, CircleAlert, Info, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { useCliPreview } from "@/lib/hooks/useClis";
import { cn } from "@/lib/utils";

function Line({ icon, tone, children }: { icon: ReactNode; tone: string; children: ReactNode }) {
  return (
    <p className={cn("flex items-start gap-[7px] text-xs leading-[1.45]", tone)}>
      <span className="pt-0.5">{icon}</span>
      <span className="min-w-0">{children}</span>
    </p>
  );
}

export function CliFound({ command }: { command: string }) {
  const { t } = useTranslation();
  const { data, isPending } = useCliPreview(command);
  const icon = "size-3";
  let lines: ReactNode;
  if (isPending) {
    return <p className="text-xs text-text-muted">{t("clis.add.looking")}</p>;
  } else if (!data) {
    return null;
  } else if (data.added) {
    lines = (
      <Line icon={<CircleAlert className={icon} aria-hidden />} tone="text-danger">
        {t("clis.add.alreadyAdded", { command: data.command })}
      </Line>
    );
  } else {
    lines = (
      <>
        {data.path ? (
          <Line
            icon={<Check className={cn(icon, "text-success")} aria-hidden />}
            tone="text-text-muted"
          >
            {t("clis.add.foundAt")} <span className="font-mono text-text">{data.path}</span>
            {data.version ? (
              <>
                {" · "}
                {t("clis.add.version")} <span className="font-mono text-text">{data.version}</span>
              </>
            ) : null}
          </Line>
        ) : (
          <Line icon={<TriangleAlert className={icon} aria-hidden />} tone="text-warning">
            {t("clis.add.notFound", { command: data.command })}
          </Line>
        )}
        {data.required ? (
          <Line icon={<Info className={icon} aria-hidden />} tone="text-text-muted">
            {t("clis.add.alsoRequired")}
          </Line>
        ) : null}
      </>
    );
  }
  return (
    <div
      aria-live="polite"
      data-testid="cli-found"
      className="flex flex-col gap-1 rounded-lg border border-border bg-surface-sunken px-2.5 py-2"
    >
      {lines}
    </div>
  );
}
