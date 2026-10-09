// src/components/custom-tools/ToolResponseTab.tsx — the tool editor's Response tab: whose rules judge this tool's
// calls (the group's, or rules of its own — an empty list judges by the HTTP status alone) and what the agent gets.
import { useTranslation } from "react-i18next";

import type { ResponseRule } from "@/lib/api/customTools";
import { describeRule } from "@/lib/customTools/responseRules";
import { ResponseRulesField } from "./ResponseRulesField";
import type { ToolForm } from "./toolForm";

interface Props {
  form: ToolForm;
  onChange: (form: ToolForm) => void;
  groupRules: readonly ResponseRule[];
}

export function ToolResponseTab({ form, onChange, groupRules }: Props) {
  const { t } = useTranslation();
  const own = form.responseRules !== null;
  const choose = (value: boolean) =>
    onChange({ ...form, responseRules: value ? groupRules.map((r) => ({ ...r })) : null });
  return (
    <>
      <section className="flex flex-col gap-2">
        <span className="text-xs font-label">{t("customTools.editor.response.success")}</span>
        <p className="text-xs text-text-muted">{t("customTools.editor.response.rule")}</p>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="radio"
            name="response-rules"
            checked={!own}
            onChange={() => choose(false)}
            className="accent-accent"
          />
          {t("customTools.editor.response.follow")}
        </label>
        {own ? null : (
          <div className="ml-6 flex flex-col gap-1 rounded-lg border border-border-subtle bg-surface-sunken px-3 py-2">
            {groupRules.length === 0 ? (
              <span className="text-xs text-text-muted">
                {t("customTools.editor.response.statusOnly")}
              </span>
            ) : (
              groupRules.map((r, i) => (
                <span key={i} className="break-all font-mono text-xs">
                  {describeRule(r)}
                </span>
              ))
            )}
          </div>
        )}
        <label className="flex items-center gap-2 text-sm">
          <input
            type="radio"
            name="response-rules"
            checked={own}
            onChange={() => choose(true)}
            className="accent-accent"
          />
          {t("customTools.editor.response.own")}
        </label>
        {own ? (
          <div className="ml-6 flex flex-col gap-2">
            <p className="text-xs text-text-muted">{t("customTools.editor.response.ownHelp")}</p>
            <ResponseRulesField
              rules={form.responseRules ?? []}
              onChange={(responseRules) => onChange({ ...form, responseRules })}
            />
          </div>
        ) : null}
      </section>
      <section className="flex flex-col gap-1.5">
        <span className="text-xs font-label">{t("customTools.editor.response.agentGets")}</span>
        <p className="rounded-lg border border-border-subtle bg-surface-sunken px-3 py-2.5 text-xs text-text-muted">
          {t("customTools.editor.response.agentGetsBody")}
        </p>
      </section>
    </>
  );
}
