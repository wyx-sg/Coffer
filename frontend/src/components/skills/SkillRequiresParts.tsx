// src/components/skills/SkillRequiresParts.tsx — the pieces of a skill's Requires tab: a command's state word, a group.
import { useTranslation } from "react-i18next";

import { Section } from "@/components/Section";
import { StatusWord } from "@/components/status/StatusWord";
import type { Cli } from "@/lib/api/clis";
import { cliTone } from "@/lib/clis/format";
import { requireColumns } from "@/lib/skills/requireColumns";
import { cn } from "@/lib/utils";

export function StateWord({ cli }: { cli: Cli | undefined }) {
  const { t } = useTranslation();
  if (!cli) return <StatusWord tone="off">{t("skills.requires.unknown")}</StatusWord>;
  const word =
    cli.status === "ready" ? t("skills.requires.found") : t(`skills.requires.state.${cli.status}`);
  return <StatusWord tone={cliTone(cli.status)}>{word}</StatusWord>;
}

/** A group: its title, the one sentence saying where it is declared, the rows. */
export function Group({
  title,
  intro,
  actions,
  testId,
  withKind = false,
  children,
}: {
  /** The group's rows carry a Kind column (tools). */
  withKind?: boolean;
  title: string;
  intro: React.ReactNode;
  actions?: React.ReactNode;
  testId: string;
  children: React.ReactNode;
}) {
  return (
    <Section
      title={title}
      actions={actions}
      gap="tight"
      testId={testId}
      className="mt-8 first:mt-0"
    >
      <p className="text-xs text-text-muted">{intro}</p>
      <ul className={cn("mt-1.5", requireColumns(withKind))}>{children}</ul>
    </Section>
  );
}
