// frontend/src/pages/sync/SyncRoundBody.tsx — the body of one round in the
// round drawer (6.5.04, SyncRunDetail): its four steps, in order, and git's
// words when it could not finish.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Camera, GitCommitHorizontal } from "lucide-react";

import { Section, SectionStack } from "@/components/Section";
import type { SyncRound } from "@/lib/api/sync";
import { changeLine } from "./syncRoundStatus";
import { clock, clockSeconds } from "./syncTime";

function Step({ title, testId, children }: { title: string; testId: string; children: ReactNode }) {
  return (
    <Section title={title} gap="snug" testId={testId}>
      {children}
    </Section>
  );
}

function Box({ children }: { children: ReactNode }) {
  return <ul className="space-y-1.5 rounded-lg bg-surface-sunken px-3 py-2.5">{children}</ul>;
}

function None({ children }: { children: ReactNode }) {
  return <p className="text-sm text-text-muted">{children}</p>;
}

export function RoundBody({ run }: { run: SyncRound }) {
  const { t } = useTranslation();
  return (
    <div className="space-y-5">
      <SectionStack>
        <Step title={t("sync.drawer.snapshot")} testId="sync-run-snapshot">
          {run.snapshot ? (
            <Box>
              <li className="flex items-center gap-2.5 text-xs">
                <Camera className="size-3.5 shrink-0 text-text-subtle" aria-hidden />
                <span className="min-w-0 flex-1 truncate font-mono text-text">{run.snapshot}</span>
                <span className="text-text-subtle">{clockSeconds(run.started_at)}</span>
              </li>
            </Box>
          ) : (
            <None>{t("sync.drawer.noSnapshot")}</None>
          )}
        </Step>
        <Step title={t("sync.drawer.pulled")} testId="sync-run-pulled">
          {run.pulled.length ? (
            <Box>
              {run.pulled.map((c) => (
                <li key={c.version} className="flex items-center gap-2.5 text-xs">
                  <GitCommitHorizontal className="size-3.5 shrink-0 text-text-subtle" aria-hidden />
                  <span className="font-mono text-text">{c.version.slice(0, 7)}</span>
                  <span className="min-w-0 flex-1 truncate text-text-muted">
                    {t("sync.drawer.pulledCommit", {
                      machine: c.machine ?? t("sync.drawer.unknownMachine"),
                      count: c.files,
                    })}
                  </span>
                  <span className="text-text-subtle">{clock(c.time)}</span>
                </li>
              ))}
            </Box>
          ) : (
            <None>{t("sync.drawer.nothingPulled")}</None>
          )}
        </Step>
        <Step title={t("sync.drawer.applied")} testId="sync-run-applied">
          {run.applied.length ? (
            <Box>
              {run.applied.map((c) => (
                <li key={c.path} className="truncate font-mono text-xs text-text">
                  {changeLine(c)}
                </li>
              ))}
            </Box>
          ) : (
            <None>{t("sync.drawer.nothingApplied")}</None>
          )}
        </Step>
        <Step title={t("sync.drawer.pushed")} testId="sync-run-pushed">
          {run.pushed.length ? (
            <Box>
              {run.pushed.map((c) => (
                <li key={c.path} className="truncate font-mono text-xs text-text">
                  {changeLine(c)}
                </li>
              ))}
            </Box>
          ) : (
            <None>{t("sync.drawer.nothingPushed")}</None>
          )}
        </Step>
      </SectionStack>
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
