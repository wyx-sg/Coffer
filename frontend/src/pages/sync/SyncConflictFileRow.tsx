// frontend/src/pages/sync/SyncConflictFileRow.tsx
//
// One file a stopped round could not merge, and the three ways to answer it.
//
//   Keep this Mac's  — answered at once; it changes nothing here.
//   Take the other's — asks first, showing what taking it changes in this
//                      file (`take_theirs`), because that one overwrites.
//   Open in editor   — the daemon writes a copy with conflict markers and the
//                      OS opens it; "Mark resolved" then answers `edited`, and
//                      a copy that still has markers is refused with the line
//                      it stopped at, shown here where it was clicked.
import { useState } from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { Check, Download, FileEdit, Laptop } from "lucide-react";

import { TableActionButton } from "@/components/table/TableActionButton";
import { Badge } from "@/components/ui/badge";
import { TableCell, TableRow } from "@/components/ui/table";
import { ApiError, translateApiError } from "@/lib/api/errors";
import type { ConflictAnswer, ConflictFile } from "@/lib/api/sync";
import { useAnswerFile, useOpenInEditor } from "@/lib/hooks/useSyncStop";
import { toneClass } from "@/lib/statusColors";
import { formatDateTime } from "@/lib/utils";
import { SyncTakeTheirsDialog } from "./SyncTakeTheirsDialog";

const when = (iso: string | null) => (iso ? formatDateTime(iso) : "—");

/** An edited copy that still has conflict markers is refused with the line it
 *  stopped at, which only the daemon's own message carries — so that one is
 *  shown verbatim, and every other refusal in the app's words. */
function refusal(t: TFunction, error: unknown): string {
  if (error instanceof ApiError && error.code === "SYNC_CONFLICT_MARKERS_LEFT") {
    return error.envelopeMessage;
  }
  return translateApiError(t, error);
}

export function SyncConflictFileRow({ file }: { file: ConflictFile }) {
  const { t } = useTranslation();
  const answer = useAnswerFile();
  const editor = useOpenInEditor();
  const [taking, setTaking] = useState(false);
  const busy = answer.isPending || editor.isPending;
  const give = (value: ConflictAnswer, onSuccess?: () => void) =>
    answer.mutate({ path: file.path, answer: value }, { onSuccess });

  return (
    <TableRow data-testid={`conflict-${file.path}`}>
      <TableCell className="font-mono text-xs">
        {file.path}
        {answer.error ? (
          <p className="mt-1 font-sans text-xs text-destructive" role="alert">
            {refusal(t, answer.error)}
          </p>
        ) : null}
      </TableCell>
      <TableCell className="text-xs">{file.area}</TableCell>
      <TableCell className="text-xs text-muted-foreground">{when(file.ours_time)}</TableCell>
      <TableCell className="text-xs text-muted-foreground">
        {when(file.theirs_time)}
        {file.theirs_machine ? <span className="block">{file.theirs_machine}</span> : null}
      </TableCell>
      <TableCell>
        <Badge variant="outline" className={toneClass(file.answer ? "ok" : "warn")}>
          {file.answer ? t(`sync.conflicts.answer.${file.answer}`) : t("sync.conflicts.unanswered")}
        </Badge>
      </TableCell>
      <TableCell className="text-right">
        <div className="flex flex-wrap justify-end gap-2">
          <TableActionButton
            icon={Laptop}
            label={t("sync.conflicts.keepMine")}
            disabled={busy}
            onClick={() => give("mine")}
          />
          <TableActionButton
            icon={Download}
            label={t("sync.conflicts.takeTheirs")}
            disabled={busy}
            onClick={() => setTaking(true)}
          />
          <TableActionButton
            icon={FileEdit}
            label={t("sync.conflicts.openEditor")}
            disabled={busy}
            onClick={() => editor.mutate(file.path)}
          />
          {file.editor_path ? (
            <TableActionButton
              icon={Check}
              label={t("sync.conflicts.markResolved")}
              disabled={busy}
              onClick={() => give("edited")}
            />
          ) : null}
        </div>
        <SyncTakeTheirsDialog
          path={file.path}
          open={taking}
          onOpenChange={(next) => {
            setTaking(next);
            if (!next) answer.reset();
          }}
          pending={answer.isPending}
          error={answer.error}
          onConfirm={() => give("theirs", () => setTaking(false))}
        />
      </TableCell>
    </TableRow>
  );
}
