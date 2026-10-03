// src/components/custom-tools/GroupDefinition.tsx — a group's definition as read-only rows (4.2.01): the name agents
// see, the base URL, the headers Coffer adds (a secret header reads `name ← 🔑 secret`, no prefix), the timeout and
// the spec it came from. Its reach is the header's Reach control, not a row here.
import { useTranslation } from "react-i18next";

import { Section } from "@/components/Section";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { agentPrefix } from "@/lib/customTools/groups";
import { formatDateTime } from "@/lib/utils";
import { AuthLine } from "./AuthLine";
import { DefinitionRow } from "./DefinitionRow";

interface Props {
  group: CustomToolGroup;
  onReimport: () => void;
}

export function GroupDefinition({ group, onReimport }: Props) {
  const { t } = useTranslation();
  const headers = group.headers;
  const authValue = headers.map((h) => h.name).join(", ") || t("customTools.definition.noAuth");

  return (
    <Section title={t("customTools.definition.title")} as="h2" gap="tight" labelled>
      <p className="text-xs text-text-muted">{t("customTools.definition.description")}</p>
      <div>
        <DefinitionRow
          label={t("customTools.definition.agentsSee")}
          value={agentPrefix(group.name)}
          mono
          copyable={false}
        />
        <DefinitionRow label={t("customTools.fields.baseUrl")} value={group.base_url} mono />
        <DefinitionRow label={t("customTools.definition.auth")} value={authValue} copyable={false}>
          {headers.length === 0 ? (
            t("customTools.definition.noAuth")
          ) : (
            <span className="flex flex-col gap-1 py-1">
              {headers.map((h) =>
                h.secret ? (
                  <AuthLine key={h.name} header={h.name} secret={h.secret} />
                ) : (
                  <span key={h.name} className="font-mono text-xs">
                    {h.name}: {h.value}
                  </span>
                ),
              )}
            </span>
          )}
        </DefinitionRow>
        <DefinitionRow
          label={t("customTools.definition.timeout")}
          value={t("customTools.definition.timeoutValue", { seconds: group.timeout_seconds })}
          copyable={false}
        />
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
