// frontend/src/components/skills/SkillVerifyDialog.tsx
// Replaces the old window.alert drift report with a styled dialog. On open it
// runs useVerifySkills and shows either "No drift detected." or a list of drift
// entries (skill_name, agent_name, kind, suggested_remedy). The endpoint always
// verifies every skill; an optional `skillNames` prop narrows the *displayed*
// entries to a chosen subset (per-row / bulk verify), so the OK state reflects
// just those skills.
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { translateApiError } from "@/lib/api/errors";
import { useVerifySkills } from "@/lib/hooks/useSkills";

export function SkillVerifyDialog({
  open,
  onOpenChange,
  skillNames,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** When set, only drift entries for these skill names are displayed. */
  skillNames?: string[];
}) {
  const { t } = useTranslation();
  const verify = useVerifySkills();
  const { mutate, reset } = verify;

  // Re-run the drift check each time the dialog opens; clear stale state on close.
  useEffect(() => {
    if (open) mutate();
    else reset();
  }, [open, mutate, reset]);

  // The endpoint verifies all skills; narrow to the chosen subset when asked.
  const allEntries = verify.data?.entries ?? [];
  const entries = skillNames
    ? allEntries.filter((d) => skillNames.includes(d.skill_name))
    : allEntries;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("skills.verify.title")}</DialogTitle>
          <DialogDescription>{t("skills.verify.subtitle")}</DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-1">
          {verify.isError ? (
            <div className="flex items-start gap-3 py-2 text-sm text-destructive" role="alert">
              <AlertCircle className="mt-0.5 size-5 shrink-0" />
              <span>{translateApiError(t, verify.error)}</span>
            </div>
          ) : /* Show the spinner until the verify mutation has actually
                completed: when idle (before the open-effect fires mutate) the
                empty entries list would otherwise flash a false "no drift". */
          !verify.isSuccess ? (
            <div className="flex items-center gap-3 py-4 text-sm text-muted-foreground">
              <Loader2 className="size-5 animate-spin" />
              {t("skills.verify.checking")}
            </div>
          ) : entries.length === 0 ? (
            <div className="flex items-center gap-2 py-2 text-sm font-medium">
              <CheckCircle2 className="size-5 text-primary" />
              {t("skills.verify.ok")}
            </div>
          ) : (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">
                {t("skills.verify.found", { count: entries.length })}
              </p>
              <ul className="space-y-2">
                {entries.map((d, i) => (
                  <li
                    key={`${d.skill_name}-${d.agent_name}-${i}`}
                    className="space-y-1 rounded-md border bg-card/60 px-3 py-2 text-sm"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{d.skill_name}</span>
                      <span className="text-muted-foreground">→</span>
                      <span>{d.agent_name}</span>
                      <Badge variant="outline">{d.kind}</Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">{d.suggested_remedy}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button onClick={() => onOpenChange(false)}>{t("common.done")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
