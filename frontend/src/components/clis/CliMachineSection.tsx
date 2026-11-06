// src/components/clis/CliMachineSection.tsx — "On this machine": where Coffer found the command, as of the last check.
//
// Nothing here acts: Coffer never runs an install (the problem banner hands
// that to an agent), and it never runs the command, so there is no version to
// show. A command that is not on PATH is drawn in the problem colour.
import { useTranslation } from "react-i18next";

import type { Cli } from "@/lib/api/clis";
import { checkedWhen } from "@/lib/clis/format";
import { CliField, CliSection } from "./CliField";

const mono = "truncate font-mono text-xs font-normal text-text";

export function CliMachineSection({ cli }: { cli: Cli }) {
  const { t, i18n } = useTranslation();
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
    </CliSection>
  );
}
