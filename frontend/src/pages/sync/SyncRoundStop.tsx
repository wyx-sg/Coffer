// frontend/src/pages/sync/SyncRoundStop.tsx — why a round stopped, in the
// round drawer (SyncRoundBody): what stopped it, in words, and the files it
// stopped on. The record keeps those files, so a round still says why once
// its stop has been answered and a later round has finished the work.
import { useTranslation } from "react-i18next";

import { ShowAllRow } from "@/components/LongList";
import { useLongList } from "@/components/useLongList";
import type { SyncRound } from "@/lib/api/sync";
import { FILE_LIST, FILE_ROW } from "./SyncChangeMark";

function PathList({ paths }: { paths: string[] }) {
  const { visible, shown, total, collapsed, expand, listClassName } = useLongList(paths);
  return (
    <div className={FILE_LIST}>
      <ul className={listClassName}>
        {visible.map((p) => (
          <li key={p} className={FILE_ROW}>
            <span className="min-w-0 flex-1 truncate font-mono text-xs text-text">{p}</span>
          </li>
        ))}
      </ul>
      {collapsed ? <ShowAllRow shown={shown} total={total} onShowAll={expand} /> : null}
    </div>
  );
}

function reason(t: ReturnType<typeof useTranslation>["t"], run: SyncRound): string {
  if (run.status === "held") {
    // A round recorded before the direction was kept says neither.
    const key =
      run.held_direction === "incoming"
        ? "heldIncoming"
        : run.held_direction === "outgoing"
          ? "heldOutgoing"
          : "held";
    return t(`sync.drawer.stop.${key}`, { count: run.held });
  }
  if (run.status === "stopped") return t("sync.drawer.stop.conflicts", { count: run.conflicts });
  return t("sync.drawer.stop.plaintext", { count: run.plaintext.length });
}

export function RoundStop({ run }: { run: SyncRound }) {
  const { t } = useTranslation();
  const paths =
    run.status === "plaintext_found"
      ? run.plaintext.map((f) => `${f.path}:${f.line} · ${f.key}`)
      : run.stopped_on;
  return (
    <section className="flex flex-col gap-2" data-testid="sync-run-stop">
      <h3 className="text-sm font-semibold text-text">{t("sync.drawer.stop.title")}</h3>
      <p className="text-sm text-text">{reason(t, run)}</p>
      {paths.length ? <PathList paths={paths} /> : null}
      <p className="text-xs text-text-muted">{t("sync.drawer.stop.after")}</p>
    </section>
  );
}
