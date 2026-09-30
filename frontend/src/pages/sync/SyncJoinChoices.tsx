// frontend/src/pages/sync/SyncJoinChoices.tsx — first join, differing files (6.5.19).
//
// The files a join found different here and on the remote. A join never
// overwrites either side on its own: each file stays exactly as it is here,
// and is not pushed, until a person keeps this Mac's version or takes the
// other Mac's. Choices are STAGED per row and sent together by "Apply N
// choices" — one POST /sync/join-choices takes the whole list — so a person
// can go down the list and change their mind before anything moves.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, ExternalLink } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Segmented } from "@/components/ui/segmented";
import { useToast } from "@/components/ui/toast";
import { fsApi } from "@/lib/api/fs";
import type { ConflictFile } from "@/lib/api/sync";
import { useSyncStatus } from "@/lib/hooks/useSync";
import { useChooseJoin, useJoinChoices } from "@/lib/hooks/useSyncStop";
import { SyncConflictDiff } from "./SyncConflictDiff";
import { roundMoment } from "./syncMachineTimes";

type Side = "mine" | "theirs";
/** Rows shown before "…and N more". */
const FIRST = 4;

function edited(t: ReturnType<typeof useTranslation>["t"], file: ConflictFile, locale: string) {
  const now = new Date();
  const when = (iso: string | null) => (iso ? roundMoment(iso, now, t, locale) : "—");
  return t("sync.joinChoices.edited", {
    mine: when(file.ours_time),
    who: file.theirs_machine ?? t("sync.joinChoices.otherMac"),
    theirs: when(file.theirs_time),
  });
}

export function SyncJoinChoices() {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const { data } = useJoinChoices(true);
  const vault = useSyncStatus().data?.vault_path ?? null;
  const choose = useChooseJoin();
  const [staged, setStaged] = useState<Record<string, Side>>({});
  const [all, setAll] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const files = data?.files ?? [];
  if (files.length === 0) return null;

  const chosen = files.filter((f) => staged[f.path]);
  const shown = all ? files : files.slice(0, FIRST);
  const apply = () =>
    choose.mutate(
      chosen.map((f) => ({ path: f.path, answer: staged[f.path] })),
      { onSuccess: () => setStaged({}) },
    );

  return (
    <Card data-testid="sync-join-choices">
      <div className="flex flex-wrap items-center gap-2 border-b border-border-subtle px-4 py-2.5">
        <h3 className="text-sm font-semibold text-text">{t("sync.joinChoices.title")}</h3>
        <span className="rounded-sm bg-chip px-1.5 text-2xs font-label text-text-muted">
          {files.length}
        </span>
        <span className="ml-auto text-xs text-text-muted">{t("sync.joinChoices.body")}</span>
        <Button
          type="button"
          size="sm"
          disabled={chosen.length === 0}
          loading={choose.isPending}
          onClick={apply}
        >
          {t("sync.joinChoices.apply", { count: chosen.length })}
        </Button>
      </div>
      <ul className="flex flex-col">
        {shown.map((file) => {
          const who = file.theirs_machine ?? t("sync.joinChoices.otherMac");
          return (
            <li
              key={file.path}
              data-testid={`join-choice-${file.path}`}
              className="flex flex-wrap items-center gap-3 border-t border-border-subtle px-4 py-2.5 first:border-t-0"
            >
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-expanded={open === file.path}
                aria-label={t("sync.joinChoices.showDiff", { path: file.path })}
                onClick={() => setOpen((o) => (o === file.path ? null : file.path))}
              >
                {open === file.path ? <ChevronDown aria-hidden /> : <ChevronRight aria-hidden />}
              </Button>
              <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span className="truncate font-mono text-xs text-text">{file.path}</span>
                <span className="text-xs text-text-muted">{edited(t, file, i18n.language)}</span>
              </div>
              {vault ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  aria-label={t("sync.joinChoices.open", { path: file.path })}
                  onClick={() =>
                    void fsApi
                      .open(`${vault}/${file.path}`)
                      .catch(() => toast.error(t("fileActions.openFailed")))
                  }
                >
                  <ExternalLink aria-hidden />
                </Button>
              ) : null}
              <Segmented<Side | "">
                label={t("sync.joinChoices.choiceFor", { path: file.path })}
                value={staged[file.path] ?? ""}
                disabled={choose.isPending}
                options={[
                  { value: "mine", label: t("sync.joinChoices.keepMine") },
                  { value: "theirs", label: t("sync.joinChoices.takeTheirs", { who }) },
                ]}
                onChange={(side) => side && setStaged((s) => ({ ...s, [file.path]: side }))}
              />
              {open === file.path ? (
                <div className="basis-full" data-testid={`join-choice-diff-${file.path}`}>
                  <p className="mb-1.5 text-xs text-text-muted">
                    {t("sync.joinChoices.diffCaption", { who })}
                  </p>
                  <SyncConflictDiff path={file.path} />
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
      {!all && files.length > FIRST ? (
        <button
          type="button"
          className="w-full border-t border-border-subtle px-4 py-2 text-left text-xs text-text-muted hover:text-text"
          onClick={() => setAll(true)}
        >
          {t("sync.joinChoices.more", { count: files.length - FIRST })}
        </button>
      ) : null}
    </Card>
  );
}
