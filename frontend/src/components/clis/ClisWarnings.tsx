// src/components/clis/ClisWarnings.tsx — the `requires:` entries the daemon skipped, as one grey line under the page subtitle (board 4.4.18).
//
// "2 requires: entries in skills couldn't be read · View" — View opens Skills,
// where the skills that carry them are. No banner: nothing here is the
// person's to fix on this page.
import { Trans, useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import type { CliWarning } from "@/lib/api/clis";

export function ClisWarnings({ warnings }: { warnings: readonly CliWarning[] }) {
  const { t } = useTranslation();
  if (warnings.length === 0) return null;
  const skills = [...new Set(warnings.map((w) => w.skill_name))].join(", ");
  return (
    <p className="text-xs text-text-muted" title={skills} data-testid="cli-warnings">
      <Trans
        i18nKey="clis.warnings.line"
        count={warnings.length}
        components={{ code: <code className="font-mono" /> }}
      />
      <span aria-hidden className="mx-1.5">
        ·
      </span>
      <Link to="/skills" className="font-label text-accent-text hover:underline">
        {t("clis.warnings.view")}
      </Link>
    </p>
  );
}
