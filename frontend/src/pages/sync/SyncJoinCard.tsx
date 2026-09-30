// frontend/src/pages/sync/SyncJoinCard.tsx
//
// A machine meets the remote for the first time by JOINING it (spec
// vault-sync), and a join is explicit: until this machine joins, rounds move
// nothing. The card asks the daemon what joining would do — applying nothing —
// and states it before the button: what comes down, by area; how many files
// are already the same; which differ (those are left here for a person to
// choose, never overwritten); what goes up; and that nothing is deleted. An
// empty remote simply receives this whole vault.
//
// A refused join (the remote is another layout, or not a vault) shows the
// daemon's reason and offers no button.
import { useTranslation } from "react-i18next";
import { LogIn } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { translateApiError } from "@/lib/api/errors";
import type { JoinPreview } from "@/lib/api/sync";
import { useJoin, useJoinPreview } from "@/lib/hooks/useSyncStop";
import { formatDateTime } from "@/lib/utils";
import { SyncRoundPathList } from "./SyncRoundPathList";

function areaLines(counts: JoinPreview["pulled"]): string[] {
  return counts.map((c) => `${c.area} · ${c.files}`);
}

function Preview({ preview }: { preview: JoinPreview }) {
  const { t } = useTranslation();
  return (
    <div className="space-y-3" data-testid="sync-join-preview">
      <p className="text-sm">{t(`sync.join.kind.${preview.kind}`)}</p>
      {preview.pushed_by ? (
        <p className="text-xs text-muted-foreground">
          {t("sync.join.lastPushed", {
            who: preview.pushed_by,
            when: preview.pushed_at ? formatDateTime(preview.pushed_at) : "—",
          })}
        </p>
      ) : null}
      <SyncRoundPathList
        titleKey="sync.join.pulled"
        items={areaLines(preview.pulled)}
        testId="sync-join-pulled"
      />
      {preview.kind !== "empty" ? (
        <p className="text-sm">{t("sync.join.same", { count: preview.same })}</p>
      ) : null}
      <SyncRoundPathList
        titleKey="sync.join.differ"
        items={preview.differ}
        tone="warn"
        testId="sync-join-differ"
      />
      <SyncRoundPathList
        titleKey="sync.join.pushed"
        items={areaLines(preview.pushed)}
        testId="sync-join-pushed"
      />
      {preview.deleted.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("sync.join.nothingDeleted")}</p>
      ) : (
        <SyncRoundPathList
          titleKey="sync.join.deleted"
          items={preview.deleted}
          tone="err"
          testId="sync-join-deleted"
        />
      )}
    </div>
  );
}

export function SyncJoinCard() {
  const { t } = useTranslation();
  const preview = useJoinPreview(true);
  const join = useJoin();
  const refused = preview.data?.refused ?? null;

  return (
    <Card data-testid="sync-join">
      <CardHeader>
        <CardTitle>{t("sync.join.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">{t("sync.join.notJoined")}</p>
        {preview.isLoading ? (
          <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : preview.error ? (
          <p className="text-sm text-destructive">{translateApiError(t, preview.error)}</p>
        ) : preview.data ? (
          <Preview preview={preview.data} />
        ) : null}
        {refused ? (
          <p className="text-sm text-destructive" role="alert">
            {refused}
          </p>
        ) : null}
        <Button
          type="button"
          disabled={!preview.data || refused !== null || join.isPending}
          onClick={() => join.mutate()}
        >
          <LogIn className="size-4" aria-hidden />
          {join.isPending ? t("sync.join.joining") : t("sync.join.join")}
        </Button>
      </CardContent>
    </Card>
  );
}
