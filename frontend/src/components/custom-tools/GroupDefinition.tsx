// src/components/custom-tools/GroupDefinition.tsx — a group's definition as read-only rows (4.2.34): its description, the
// name agents see, the timeout and the spec it came from. Where its calls go — base URLs, headers, secrets and
// variables — is each environment's, under Environments, however many it has. Its reach is the header's Reach control, not a row here.
import { useTranslation } from "react-i18next";

import { Section } from "@/components/Section";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { agentPrefix } from "@/lib/customTools/groups";
import { describeRule } from "@/lib/customTools/responseRules";
import { formatDateTime } from "@/lib/utils";
import { DefinitionRow } from "./DefinitionRow";

interface Props {
  group: CustomToolGroup;
  onReimport: () => void;
}

export function GroupDefinition({ group, onReimport }: Props) {
  const { t } = useTranslation();
  const diagnostic = group.response?.diagnostic_headers ?? [];
  const rules = group.response?.rules ?? [];
  const statusOnly = t("customTools.definition.statusOnly");

  return (
    <Section title={t("customTools.definition.title")} as="h2" gap="tight" labelled>
      <p className="text-xs text-text-muted">{t("customTools.definition.description")}</p>
      <div>
        {group.description ? (
          <DefinitionRow
            label={t("customTools.editGroup.description")}
            value={group.description}
            copyable={false}
          />
        ) : null}
        <DefinitionRow
          label={t("customTools.definition.agentsSee")}
          value={agentPrefix(group.name)}
          mono
          copyable={false}
        />
        <DefinitionRow
          label={t("customTools.definition.timeout")}
          value={t("customTools.definition.timeoutValue", { seconds: group.timeout_seconds })}
          copyable={false}
        />
        <DefinitionRow
          label={t("customTools.definition.diagnosticHeaders")}
          value={diagnostic.length > 0 ? diagnostic.join(", ") : t("customTools.definition.none")}
          mono={diagnostic.length > 0}
          copyable={false}
        />
        <DefinitionRow
          label={t("customTools.definition.responseRules")}
          value={rules.length > 0 ? rules.map(describeRule).join("\n") : statusOnly}
          copyable={false}
        >
          {rules.length > 0 ? (
            <span className="flex flex-col gap-0.5 whitespace-normal py-1.5">
              {rules.map((r, i) => (
                <span key={i} className="break-all font-mono text-xs">
                  {describeRule(r)}
                </span>
              ))}
            </span>
          ) : (
            statusOnly
          )}
        </DefinitionRow>
        {group.source ? (
          <DefinitionRow
            label={t("customTools.definition.spec")}
            value={group.source.location}
            mono
            trailing={
              <>
                <span className="shrink-0 text-xs text-text-muted">
                  {t("customTools.definition.fetched", {
                    date: formatDateTime(group.source.fetched_at),
                  })}
                </span>
                <button
                  type="button"
                  className="shrink-0 text-xs font-label text-accent-text hover:underline"
                  onClick={onReimport}
                >
                  {t("customTools.reimport.action")}
                </button>
              </>
            }
          />
        ) : null}
      </div>
    </Section>
  );
}
