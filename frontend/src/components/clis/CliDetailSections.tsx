// src/components/clis/CliDetailSections.tsx — the body of a CLI's page: Command, Login and Needed by, as read-only rows.
//
// The only actions here are the confirmation-gated Install… / Update… beside
// the Homebrew command and Copy beside the login command — Coffer never runs a
// login. Each skill under Needed by opens that skill's Requires tab.
import { Check, Copy } from "lucide-react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import type { Cli } from "@/lib/api/clis";
import { isInstallable } from "@/lib/clis/format";
import { useCopyText } from "@/lib/hooks/useCopyText";
import { CliActionButton } from "./CliActionButton";
import { CliField, CliSection } from "./CliField";

interface Props {
  cli: Cli;
  onInstall: (cli: Cli) => void;
}

export function CliDetailSections({ cli, onInstall }: Props) {
  const { t } = useTranslation();
  const { copied, copy } = useCopyText();
  const loginCommand = cli.login.command;
  const versionOk = cli.status !== "missing" && cli.status !== "outdated";

  return (
    <div className="space-y-6">
      <CliSection title={t("clis.detail.sections.command")}>
        <CliField label={t("clis.detail.foundAt")}>
          {cli.path ? (
            <span className="font-mono text-xs">{cli.path}</span>
          ) : (
            <span className="text-danger">{t("clis.notOnPath")}</span>
          )}
        </CliField>
        <CliField label={t("clis.detail.version")}>
          <span className="font-mono text-xs">
            {cli.version ?? (cli.path ? t("clis.unknownVersion") : "—")}
          </span>
          {cli.min_version ? (
            <span className="ml-2 text-xs text-text-muted">
              {versionOk && cli.version ? "✓ " : ""}
              {t("clis.needs", { version: cli.min_version })}
            </span>
          ) : null}
        </CliField>
        {isInstallable(cli) ? (
          <CliField
            label={t(
              cli.status === "outdated" ? "clis.detail.updateWith" : "clis.detail.installWith",
            )}
            trailing={<CliActionButton cli={cli} onInstall={onInstall} />}
          >
            <code className="font-mono text-xs">{cli.install_command}</code>
          </CliField>
        ) : null}
      </CliSection>

      <CliSection title={t("clis.detail.sections.login")}>
        <CliField label={t("clis.detail.state")}>
          {cli.login.state ? t(`clis.login.${cli.login.state}`) : "—"}
        </CliField>
        {loginCommand ? (
          <CliField
            label={t("clis.detail.loginWith")}
            trailing={
              <Button type="button" variant="outline" size="sm" onClick={() => copy(loginCommand)}>
                {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
                {copied ? t("clis.actions.copied") : t("clis.actions.copy")}
              </Button>
            }
          >
            <code className="font-mono text-xs">{loginCommand}</code>
            <p className="text-xs text-text-muted">{t("clis.detail.loginHint")}</p>
          </CliField>
        ) : null}
      </CliSection>

      <CliSection
        title={
          <>
            {t("clis.detail.sections.neededBy")}
            <span className="ml-2 font-normal text-text-muted">
              {t("clis.skillCount", { count: cli.needed_by.length })}
            </span>
          </>
        }
      >
        {cli.needed_by.map((need) => (
          <CliField
            key={need.skill_uid}
            label={
              <Link
                to={`/skills/${encodeURIComponent(need.skill_name)}/requires`}
                className="font-mono text-sm text-accent-text hover:underline"
              >
                {need.skill_name}
              </Link>
            }
          >
            <span className="text-xs text-text-muted">
              {[need.min_version ? t("clis.needs", { version: need.min_version }) : null, need.why]
                .filter(Boolean)
                .join(" · ") || "—"}
            </span>
          </CliField>
        ))}
      </CliSection>
    </div>
  );
}
