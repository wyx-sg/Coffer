// src/components/secret/ScanIgnoredList.tsx — the findings a person said are not secrets, behind "Show ignored (N)".
//
// Each carries "Report again", which forgets the value so the scan reports it
// (spec secret "Remember a value a person says is not a secret"). Renders
// nothing when there are none.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import type { SecretScanFinding } from "@/lib/api/secret";
import { placeOf } from "./scanPlan";

interface Props {
  ignored: SecretScanFinding[];
  busy: boolean;
  onReportAgain: (id: string) => void;
}

export function ScanIgnoredList({ ignored, busy, onReportAgain }: Props) {
  const { t } = useTranslation();
  const [shown, setShown] = useState(false);
  if (ignored.length === 0) return null;
  return (
    <div className="text-xs">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        aria-expanded={shown}
        onClick={() => setShown(!shown)}
      >
        {shown
          ? t("secrets.scan.hideIgnored")
          : t("secrets.scan.showIgnored", { count: ignored.length })}
      </Button>
      {shown ? (
        <ul className="mt-1 divide-y divide-border-subtle rounded-md border border-border-subtle">
          {ignored.map((f) => (
            <li key={f.id} className="flex items-center gap-3 px-3 py-1.5 text-text-muted">
              <span className="w-[26%] shrink-0 truncate" title={f.resource}>
                {f.resource}
              </span>
              <span className="min-w-0 flex-1 truncate font-mono" title={placeOf(f)}>
                {placeOf(f)}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={busy}
                aria-label={t("secrets.scan.reportAgainOne", {
                  resource: f.resource,
                  place: placeOf(f),
                })}
                onClick={() => onReportAgain(f.id)}
              >
                {t("secrets.scan.reportAgain")}
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
