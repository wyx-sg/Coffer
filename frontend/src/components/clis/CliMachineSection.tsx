// src/components/clis/CliMachineSection.tsx — "On this machine": where Coffer found the command and its version, as of the last check.
//
// Nothing here acts: Coffer never runs an install or an update (the problem
// banner hands those to an agent). A version below the minimum, and a command
// that is not on PATH, are drawn in their problem colour; a minimum Coffer
// cannot compare because the command printed no version says so.
import { useTranslation } from "react-i18next";

import type { Cli } from "@/lib/api/clis";
import { checkedWhen } from "@/lib/clis/format";
import { CliField, CliSection } from "./CliField";

const mono = "truncate font-mono text-xs font-normal text-text";

export function CliMachineSection({ cli }: { cli: Cli }) {
  const { t, i18n } = useTranslation();
  const outdated = cli.status === "outdated";
  return (
    <CliSection
      title={t("clis.detail.sections.machine")}
      note={t("clis.detail.machineNote", {
        when: checkedWhen(t, cli.checked_at, i18n.language),
      })}
    >
      <CliField label={t("clis.detail.foundAt")}>
        {cli.path ? (
          <span className={mono}>{cli.path}</span>
        ) : (
          <span className="text-danger">{t("clis.notOnPath")}</span>
        )}
      </CliField>
      <CliField label={t("clis.detail.version")}>
        {cli.version ? (
          <span className={mono}>{cli.version}</span>
        ) : (
          <span className="text-text-muted">{cli.path ? t("clis.unknownVersion") : "—"}</span>
        )}
        {cli.min_version ? (
          <span className={outdated ? "text-xs text-warning" : "text-xs text-text-muted"}>
            {t(cli.version_unverifiable ? "clis.versionUnverifiable" : "clis.needs", {
              version: cli.min_version,
            })}
          </span>
        ) : null}
      </CliField>
    </CliSection>
  );
}
