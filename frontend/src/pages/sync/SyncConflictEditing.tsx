// frontend/src/pages/sync/SyncConflictEditing.tsx
//
// A file open in the person's editor (6.5.07): edit the marked-up copy to the
// version wanted, save it, then Mark resolved — which answers `edited` from
// the copy as saved and is refused, with the line, while a conflict marker is
// left in it. "The file as saved" shows that copy, re-read whenever this
// window regains focus (the person saves in the editor, then comes back).
// Back to two choices leaves the editor behind; the copy stays where it is.
import { AlertTriangle, Pencil } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import type { ConflictFile } from "@/lib/api/sync";
import { useFileVersions } from "@/lib/hooks/useSyncStop";
import { cn } from "@/lib/utils";
import { refusal } from "./syncConflictFormat";

interface Props {
  file: ConflictFile;
  pending: boolean;
  error: unknown;
  onResolve: () => void;
  onBack: () => void;
}

const MARKER = /^(<{7}|={7}|>{7})(\s|$)/;

function Saved({ text }: { text: string }) {
  return (
    <pre
      className="overflow-auto rounded-lg bg-surface-sunken px-3 py-3 font-mono text-xs leading-5 text-text"
      data-testid="sync-conflict-saved"
    >
      {text.split("\n").map((line, i) => (
        <span
          key={i}
          className={cn("block min-h-5", MARKER.test(line) && "bg-danger-soft text-danger")}
        >
          {line}
        </span>
      ))}
    </pre>
  );
}

export function SyncConflictEditing({ file, pending, error, onResolve, onBack }: Props) {
  const { t } = useTranslation();
  const versions = useFileVersions(file.path, true, { live: true });
  const saved = versions.data?.edited ?? null;

  return (
    <>
      <div className="flex items-start gap-3 rounded-xl border border-border bg-surface-raised p-4">
        <span className="inline-flex size-7 shrink-0 items-center justify-center rounded-lg bg-warning-soft text-warning">
          <Pencil className="size-3.5" aria-hidden />
        </span>
        <div className="flex min-w-0 flex-col gap-1.5">
          <p className="text-sm font-label text-text">{t("sync.resolve.editing.title")}</p>
          <p className="text-xs text-text-muted">{t("sync.resolve.editing.body")}</p>
          {error ? (
            <p className="flex items-start gap-1.5 text-xs text-danger" role="alert">
              <AlertTriangle className="mt-px size-3.5 shrink-0" aria-hidden />
              {refusal(t, error)}
            </p>
          ) : null}
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <Button type="button" size="sm" loading={pending} onClick={onResolve}>
              {t("sync.resolve.editing.markResolved")}
            </Button>
            <Button type="button" size="sm" variant="ghost" disabled={pending} onClick={onBack}>
              {t("sync.resolve.editing.back")}
            </Button>
          </div>
        </div>
      </div>
      <section className="flex flex-col gap-2" aria-label={t("sync.resolve.editing.saved")}>
        <h3 className="text-2xs font-semibold uppercase tracking-[.02em] text-text-muted">
          {t("sync.resolve.editing.saved")}
        </h3>
        {saved !== null ? (
          <Saved text={saved} />
        ) : versions.isLoading ? null : (
          <p className="text-xs text-text-muted">{t("sync.resolve.editing.notSaved")}</p>
        )}
      </section>
    </>
  );
}
