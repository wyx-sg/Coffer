// frontend/src/components/skills/SkillSourceChangeReview.tsx
// The step after Check source in Change source (spec skill-manager "Change a
// Git-imported skill's source"; web-ui "changing a skill's source shows the
// change before anything is replaced"): the names of the files that would be
// added, removed or changed against the skill's current folder — names only,
// no diff — and a button to take it. Cancel, or closing, drops the stage.
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DialogErrorBanner } from "@/components/ui/confirm-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { translateApiError } from "@/lib/api/errors";
import type { SkillSourceChange, SkillSourceChangeFile } from "@/lib/api/skills";

const CHIP: Record<SkillSourceChangeFile["status"], "success" | "destructive" | "secondary"> = {
  added: "success",
  removed: "destructive",
  modified: "secondary",
};

interface Props {
  open: boolean;
  /** The dialog's title: "Change source of <skill>". */
  title: string;
  /** Where the new source is: repository, folder and commit. */
  subtitle: string;
  change: SkillSourceChange;
  takeLabel: string;
  pending: boolean;
  error: unknown;
  onTake: () => void;
  onCancel: () => void;
}

export function SkillSourceChangeReview({
  open,
  title,
  subtitle,
  change,
  takeLabel,
  pending,
  error,
  onTake,
  onCancel,
}: Props) {
  const { t } = useTranslation();
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onCancel()}>
      <DialogContent className="flex max-h-[calc(100vh-4rem)] max-w-[480px] flex-col gap-0 overflow-hidden p-0">
        <DialogHeader className="mb-0 shrink-0 gap-[3px] pb-0 pl-5 pr-12 pt-4">
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription className="font-mono text-xs">{subtitle}</DialogDescription>
        </DialogHeader>
        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-5 pb-[18px] pt-4">
          <p className="text-sm text-text-muted">
            {change.files.length === 0
              ? t("skills.changeSource.noFiles")
              : t("skills.changeSource.filesChange", { count: change.files.length })}
          </p>
          {change.files.length > 0 ? (
            <ul className="flex flex-col gap-1.5" data-testid="source-change-files">
              {change.files.map((file) => (
                <li key={file.path} className="flex items-center gap-2 text-sm">
                  <Badge variant={CHIP[file.status]}>
                    {t(`skills.changeSource.status.${file.status}`)}
                  </Badge>
                  <span className="min-w-0 truncate font-mono text-xs">{file.path}</span>
                </li>
              ))}
            </ul>
          ) : null}
          {error ? (
            <DialogErrorBanner
              title={t("skills.changeSource.failed")}
              message={translateApiError(t, error)}
            />
          ) : null}
        </div>
        <DialogFooter className="m-0 mt-0 flex-row items-center justify-start gap-2 rounded-none px-5 py-3 sm:justify-start">
          <span className="min-w-0 text-xs text-text-muted">{t("skills.changeSource.note")}</span>
          <span className="ml-auto flex shrink-0 gap-2">
            <Button variant="ghost" onClick={onCancel} disabled={pending}>
              {t("common.cancel")}
            </Button>
            <Button loading={pending} onClick={onTake}>
              {takeLabel}
            </Button>
          </span>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
