// frontend/src/pages/sync/SyncEmptyRemote.tsx — setup, empty remote (6.4.21).
//
// The repository Check repository found is empty, so this Mac becomes the
// first machine and the first round pushes the whole vault: said with what
// that is, from the status's own counts, before anything is saved. Push and
// start syncing stores the remote and joins it; Back returns to the form.
import { useTranslation } from "react-i18next";
import { Check, Copy, Info } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { SyncStatus } from "@/lib/api/sync";
import { useCopyText } from "@/lib/hooks/useCopyText";
import { JoinLine } from "./SyncJoinLine";

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
    <div className="flex max-w-[680px] flex-col gap-4" data-testid="sync-setup-empty">
      <div className="flex flex-col gap-2.5">
        <div className="flex flex-col gap-0.5">
          <h2 className="text-md font-semibold text-text">{t("sync.setup.empty.title")}</h2>
          <p className="text-xs text-text-muted">{t("sync.setup.empty.body")}</p>
        </div>
        <ul className="overflow-hidden rounded-xl border border-border bg-surface-raised">
          {rows.map((row) => (
            <JoinLine key={row.dir} mark="+" title={`${row.dir} · ${row.label}`} />
          ))}
        </ul>
        {includeSecret ? null : (
          <p className="flex items-start gap-2 text-xs leading-[1.45] text-text-muted">
            <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            {t("sync.setup.empty.noSecrets")}
          </p>
        )}
      </div>
      <div className="flex items-center gap-2">
        <Button type="button" loading={pending} onClick={onPush}>
          {t("sync.setup.empty.push")}
        </Button>
        <Button type="button" variant="ghost" disabled={pending} onClick={onBack}>
          {t("sync.setup.back")}
        </Button>
        <span className="ml-auto flex min-w-0 items-center gap-1">
          <span className="truncate font-mono text-xs text-text-subtle">{url}</span>
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
    </div>
  );
}
