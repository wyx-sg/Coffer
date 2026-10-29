// src/components/scheduled-tasks/WorkerPane.tsx — one of Coffer's own background workers, read-only: what it does, how it is woken, and what it did last.
//
// Spec daemon "Show Coffer's own background work beside the owner's tasks".
// Nothing here starts, pauses or changes a worker: they are Coffer's.
import { Cog } from "lucide-react";
import { useTranslation } from "react-i18next";

import { RelativeTime } from "@/components/RelativeTime";
import { Section } from "@/components/Section";
import { StatusPill } from "@/components/status/StatusPill";
import type { DaemonWorker } from "@/lib/api/daemon";
import { workerDescription, workerLabel, workerTone } from "@/lib/scheduledTasks/format";
import { formatMoment } from "@/lib/time";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[140px_minmax(0,1fr)] gap-3 py-1.5 text-xs">
      <dt className="text-text-muted">{label}</dt>
      <dd className="min-w-0 text-text">{children}</dd>
    </div>
  );
}

export function WorkerPane({ worker }: { worker: DaemonWorker }) {
  const { t, i18n } = useTranslation();
  const description = workerDescription(t, worker.name);
  return (
    <div className="flex flex-col gap-5">
      <header className="flex min-w-0 items-start gap-3">
        <span className="mt-0.5 inline-flex size-8 shrink-0 items-center justify-center rounded-lg border border-border-subtle bg-surface-sunken text-text-muted">
          <Cog className="size-4" strokeWidth={1.75} aria-hidden />
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <div className="flex min-w-0 items-center gap-2">
            <h2 className="min-w-0 truncate text-lg font-semibold text-text">
              {workerLabel(t, worker.name)}
            </h2>
            <StatusPill tone={workerTone(worker)}>
              {t(`scheduledTasks.internal.state.${worker.state}`)}
            </StatusPill>
          </div>
          <p className="min-w-0 truncate font-mono text-xs text-text-muted">{worker.name}</p>
          {description ? <p className="text-xs text-text-muted">{description}</p> : null}
        </div>
      </header>
      <Section title={t("scheduledTasks.internal.title")} help={t("scheduledTasks.internal.help")}>
        <dl className="divide-y divide-border-subtle">
          <Row label={t("scheduledTasks.internal.wakes")}>
            {t(`scheduledTasks.internal.mode.${worker.mode}`)}
          </Row>
          <Row label={t("scheduledTasks.internal.last")}>
            {worker.last_started_at ? <RelativeTime iso={worker.last_started_at} /> : "—"}
            {worker.last_duration_ms !== null
              ? ` · ${t("scheduledTasks.internal.took", { ms: worker.last_duration_ms })}`
              : null}
            {worker.last_ok === false ? ` · ${t("scheduledTasks.internal.failed")}` : null}
          </Row>
          <Row label={t("scheduledTasks.internal.next")}>
            {worker.next_run_at ? formatMoment(worker.next_run_at, i18n.language, t) : "—"}
          </Row>
          <Row label={t("scheduledTasks.internal.runs")}>
            {t("scheduledTasks.internal.runsCount", {
              runs: worker.runs,
              failures: worker.failures,
            })}
          </Row>
        </dl>
      </Section>
    </div>
  );
}
