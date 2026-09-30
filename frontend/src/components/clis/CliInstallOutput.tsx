// src/components/clis/CliInstallOutput.tsx — a running or finished Homebrew job: its output and how it ended.
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

import { StatusWord } from "@/components/status/StatusWord";
import type { CliInstall } from "@/lib/api/clis";

interface Props {
  job: CliInstall | null;
  lines: string[];
}

export function CliInstallOutput({ job, lines }: Props) {
  const { t } = useTranslation();
  const pane = useRef<HTMLPreElement>(null);
  // Follow the tail as lines arrive.
  useEffect(() => {
    const el = pane.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines.length]);

  const state = job?.state ?? "running";
  const code = job?.exit_code;
  return (
    <div className="space-y-2">
      <pre
        ref={pane}
        aria-label={t("clis.install.outputLabel")}
        className="max-h-72 min-h-24 overflow-auto whitespace-pre-wrap break-all rounded-md border border-border-subtle bg-surface-sunken p-3 font-mono text-2xs leading-relaxed text-text"
      >
        {lines.length > 0 ? lines.join("\n") : t("clis.install.noOutput")}
      </pre>
      <p className="text-xs" role="status">
        {state === "running" ? (
          <span className="text-text-muted">{t("clis.install.running")}</span>
        ) : state === "succeeded" ? (
          <StatusWord tone="ok">{t("clis.install.succeeded", { code: code ?? 0 })}</StatusWord>
        ) : (
          <StatusWord tone="err">
            {code === null || code === undefined
              ? t("clis.install.failedNoCode")
              : t("clis.install.failed", { code })}
          </StatusWord>
        )}
      </p>
    </div>
  );
}
