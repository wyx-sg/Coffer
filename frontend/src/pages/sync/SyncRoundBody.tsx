// frontend/src/pages/sync/SyncRoundBody.tsx — the body of one round in the
// round drawer (6.4.04, SyncRunDetail): its four steps, in order, and git's
// words when it could not finish.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { ShowAllRow } from "@/components/LongList";
import { useLongList } from "@/components/useLongList";
import type { SyncChange, SyncRound } from "@/lib/api/sync";
import { ChangeMark, FILE_LIST, FILE_ROW } from "./SyncChangeMark";
import { clock, clockSeconds } from "./syncTime";

/** "1  Safety snapshot": a 13/600 title with its step number in grey. */
function Step({
  number,
  title,
  testId,
  children,
}: {
  number: number;
  title: string;
  testId: string;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-2" data-testid={testId}>
      <h3 className="text-sm font-semibold text-text">
        <span className="mr-2 font-medium text-text-subtle">{number}</span>
        {title}
      </h3>
      {children}
    </section>
  );
}

function None({ children }: { children: ReactNode }) {
  return <p className="text-sm text-text-muted">{children}</p>;
}

/** A step's files: five rows, then "Showing 5 of 23 · Show all". */
function ChangeBox({ changes }: { changes: SyncChange[] }) {
  const { visible, shown, total, collapsed, expand, listClassName } = useLongList(changes);
  return (
    <div className={FILE_LIST}>
      <ul className={listClassName}>
        {visible.map((c) => (
          <li key={c.path} className={FILE_ROW}>
            <ChangeMark status={c.status} />
            <span className="min-w-0 flex-1 truncate font-mono text-xs text-text">{c.path}</span>
          </li>
        ))}
      </ul>
      {collapsed ? <ShowAllRow shown={shown} total={total} onShowAll={expand} /> : null}
    </div>
  );
}

export function RoundBody({ run }: { run: SyncRound }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-5">
      <Step number={1} title={t("sync.drawer.snapshot")} testId="sync-run-snapshot">
        {run.snapshot ? (
          <div className={FILE_LIST}>
            <div className={FILE_ROW}>
              <span className="min-w-0 flex-1 truncate font-mono text-xs text-text">
                {run.snapshot}
              </span>
              <span className="text-xs text-text-subtle">{clockSeconds(run.started_at)}</span>
            </div>
          </div>
        ) : (
          <None>{t("sync.drawer.noSnapshot")}</None>
        )}
      </Step>
      <Step number={2} title={t("sync.drawer.pulled")} testId="sync-run-pulled">
        {run.pulled.length ? (
          <div className={FILE_LIST}>
            {run.pulled.map((c) => (
              <div key={c.version} className={FILE_ROW}>
                <span className="font-mono text-xs text-text-subtle">{c.version.slice(0, 7)}</span>
                <span className="min-w-0 flex-1 truncate font-mono text-xs text-text">
                  {t("sync.drawer.pulledCommit", {
                    machine: c.machine ?? t("sync.drawer.unknownMachine"),
                    count: c.files,
                  })}
                </span>
                <span className="text-xs text-text-subtle">{clock(c.time)}</span>
              </div>
            ))}
          </div>
        ) : (
          <None>{t("sync.drawer.nothingPulled")}</None>
        )}
      </Step>
      <Step number={3} title={t("sync.drawer.applied")} testId="sync-run-applied">
        {run.applied.length ? (
          <ChangeBox changes={run.applied} />
        ) : (
          <None>{t("sync.drawer.nothingApplied")}</None>
        )}
      </Step>
      <Step number={4} title={t("sync.drawer.pushed")} testId="sync-run-pushed">
        {run.pushed.length ? (
          <ChangeBox changes={run.pushed} />
        ) : (
          <None>{t("sync.drawer.nothingPushed")}</None>
        )}
      </Step>
      {/* The daemon scrubbed any push token out of this before storing it. */}
      {run.detail ? (
        <pre
          className="whitespace-pre-wrap break-words rounded-lg bg-surface-sunken px-3 py-2.5 font-mono text-xs text-danger"
          role="alert"
        >
          {run.path ? `${run.path}: ` : ""}
          {run.detail}
        </pre>
      ) : null}
    </div>
  );
}
