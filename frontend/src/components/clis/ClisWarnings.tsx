// src/components/clis/ClisWarnings.tsx — the `requires:` entries the daemon skipped, as a small note.
import { TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import type { CliWarning } from "@/lib/api/clis";

export function ClisWarnings({ warnings }: { warnings: readonly CliWarning[] }) {
  const { t } = useTranslation();
  if (warnings.length === 0) return null;
  return (
    <Alert variant="warning">
      <TriangleAlert aria-hidden />
      <AlertTitle>{t("clis.warnings.title")}</AlertTitle>
      <AlertDescription>
        <ul className="space-y-0.5">
          {warnings.map((w, i) => (
            <li key={`${w.skill_uid}-${i}`}>
              {t("clis.warnings.line", { skill: w.skill_name, message: w.message })}
            </li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
}
