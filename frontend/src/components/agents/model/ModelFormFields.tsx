// src/components/agents/model/ModelFormFields.tsx — the fields of the Change model dialog (boards 2.1.16, 2.1.17, 2.1.19, 2.1.65).
//
// Which fields show follows the agent and the provider: the built-in login is a
// provider and one line (it sets no model or tiers); a provider adds
// Model and, for Claude Code, Model per tier. Codex has one model per session, so no tiers.
import { Trans, useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { AgentType } from "@/lib/api/agents";
import { BUILTIN, type ConnectionDraft } from "@/lib/hooks/useAgentConnectionDraft";
import { agentTypeLabel } from "@/lib/agents/display";
import { displayName } from "@/lib/resourceTitle";

const K = "agents.changeModel";
const HINT = "text-xs text-text-subtle";

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <Label htmlFor={htmlFor} className="text-sm font-medium">
        {label}
      </Label>
      {children}
    </div>
  );
}

export function ModelFormFields({
  agentType,
  draft: c,
  onNavigate,
}: {
  agentType: AgentType;
  draft: ConnectionDraft;
  /** Called when a link in the form leaves for another page (the dialog closes). */
  onNavigate?: () => void;
}) {
  const { t } = useTranslation();
  const agent = agentTypeLabel(agentType);
  const builtin = t(`agents.overviewTab.model.builtin.${agentType}`);
  const none = c.compatible.length === 0;
  return (
    <>
      <Field label={t(`${K}.provider.label`)} htmlFor="change-model-provider">
        <Select value={c.draftConn} onValueChange={c.pickConnection}>
          <SelectTrigger id="change-model-provider">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={BUILTIN}>{builtin}</SelectItem>
            {c.compatible.map((p) => (
              <SelectItem key={p.uid} value={p.uid}>
                {displayName(p)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className={HINT}>
          {none ? (
            <Trans
              i18nKey={`${K}.provider.none`}
              components={{
                link: (
                  <Link
                    to="/model-providers"
                    onClick={onNavigate}
                    className="font-label text-accent-text hover:underline"
                  />
                ),
              }}
            />
          ) : (
            t(`${K}.provider.hint.${agentType}`)
          )}
        </span>
      </Field>

      {c.draftIsBuiltin ? (
        <p className={HINT}>
          <Trans
            i18nKey={`${K}.builtinNote.${agentType}`}
            values={{ agent }}
            components={{ code: <code className="font-mono text-text-muted" /> }}
          />
        </p>
      ) : (
        <>
          <Field label={t(`${K}.model.label`)} htmlFor="change-model-model">
            <Select
              value={c.draftModel}
              onValueChange={c.pickModel}
              onOpenChange={(open) => open && c.introspect()}
            >
              <SelectTrigger id="change-model-model" className="font-mono text-xs">
                <SelectValue placeholder={t(`${K}.model.placeholder`)} />
              </SelectTrigger>
              <SelectContent>
                {c.models.map((m) => (
                  <SelectItem key={m} value={m} className="font-mono text-xs">
                    {m}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>

          {c.showTiers ? <TierFields draft={c} /> : null}
        </>
      )}
    </>
  );
}

function TierFields({ draft: c }: { draft: ConnectionDraft }) {
  const { t } = useTranslation();
  // A pinned tier stays selectable even when the list no longer offers it.
  const options = [...new Set([...c.models, ...Object.values(c.draftTiers)])].filter(Boolean);
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <span className="text-sm font-medium text-text">{t(`${K}.tiers.label`)}</span>
      {c.tiers.map((tier) => (
        <div key={tier} className="grid grid-cols-[70px_minmax(0,1fr)] items-center gap-3">
          <label htmlFor={`change-model-tier-${tier}`} className="text-xs text-text-muted">
            {t(`${K}.tiers.names.${tier}`)}
          </label>
          <Select
            value={c.draftTiers[tier] ?? ""}
            onValueChange={(m) => c.pickTier(tier, m)}
            onOpenChange={(open) => open && c.introspect()}
          >
            <SelectTrigger id={`change-model-tier-${tier}`} className="font-mono text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {options.map((m) => (
                <SelectItem key={m} value={m} className="font-mono text-xs">
                  {m}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      ))}
      <span className={HINT}>{t(`${K}.tiers.hint`)}</span>
    </div>
  );
}
