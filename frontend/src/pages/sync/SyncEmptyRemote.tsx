// frontend/src/pages/sync/SyncEmptyRemote.tsx — setup, empty remote (6.5.17).
//
// The repository Check repository found is empty, so this Mac becomes the
// first machine and the first round pushes the whole vault: said with what
// that is, from the status's own counts, before anything is saved. Push and
// start syncing stores the remote and joins it; Back returns to the form.
import { useTranslation } from "react-i18next";
import { ArrowUp, Check, Copy, Lock } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { SyncStatus } from "@/lib/api/sync";
import { useCopyText } from "@/lib/hooks/useCopyText";

interface Props {
  status: SyncStatus;
  url: string;
  includeSecret: boolean;
  pending: boolean;
  onPush: () => void;
  onBack: () => void;
}

export function SyncEmptyRemote({ status, url, includeSecret, pending, onPush, onBack }: Props) {
  const { t } = useTranslation();
  const { copied, copy } = useCopyText();
  const { areas } = status;
  const rows = [
    { dir: "knowledge/", label: t("sync.setup.empty.files", { count: areas.knowledge_documents }) },
    { dir: "skills/", label: t("sync.setup.empty.skills", { count: areas.skills }) },
    { dir: "resources/", label: t("sync.setup.empty.definitions", { count: areas.resources }) },
    ...(includeSecret
      ? [{ dir: "secret/", label: t("sync.setup.empty.secrets", { count: areas.secrets }) }]
      : []),
  ];

  return (
    <Card className="max-w-[680px]" data-testid="sync-setup-empty">
      <div className="flex flex-col gap-3 p-4">
        <div className="flex items-start gap-3">
          <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent-text">
            <ArrowUp className="size-4" aria-hidden />
          </span>
          <div className="flex flex-col gap-0.5">
            <h3 className="text-sm font-semibold text-text">{t("sync.setup.empty.title")}</h3>
            <p className="text-xs text-text-muted">{t("sync.setup.empty.body")}</p>
          </div>
        </div>
        <ul className="flex flex-col gap-1 rounded-lg bg-surface-sunken px-3 py-2.5">
          {rows.map((row) => (
            <li key={row.dir} className="flex items-center justify-between gap-4 text-xs">
              <span className="font-mono text-text">+ {row.dir}</span>
              <span className="text-text-muted">{row.label}</span>
            </li>
          ))}
        </ul>
        {includeSecret ? null : (
          <p className="flex items-center gap-1.5 text-xs text-text-muted">
            <Lock className="size-3.5" aria-hidden />
            {t("sync.setup.empty.noSecrets")}
          </p>
        )}
      </div>
      <div className="flex items-center gap-2 rounded-b-xl border-t border-border-subtle bg-surface-footer px-4 py-3">
        <Button type="button" loading={pending} onClick={onPush}>
          {t("sync.setup.empty.push")}
        </Button>
        <Button type="button" variant="ghost" disabled={pending} onClick={onBack}>
          {t("sync.setup.back")}
        </Button>
        <span className="ml-auto flex min-w-0 items-center gap-1">
          <span className="truncate font-mono text-xs text-text-muted">{url}</span>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label={t("sync.setup.copyUrl")}
            onClick={() => copy(url)}
          >
            {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
          </Button>
        </span>
      </div>
    </Card>
  );
}
