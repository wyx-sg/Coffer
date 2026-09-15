// frontend/src/components/agents/AgentManualAddForm.tsx — spec agent-registry.
// The "Add manually" disclosure + form inside the Add-agent dialog: agent type
// + optional name + config_dir picker. The dialog owns the register mutation
// and the footer's Register button (which submits this form by id, so the
// footer stays one [Cancel][Register] row); the form collects the values,
// hands them to `onSubmit`, and shows a rejected submit inline so the user can
// fix the field and retry. The folder the user picks IS the config dir;
// skills are delivered to `<config_dir>/skills`.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight } from "lucide-react";

import { FolderPickerField } from "@/components/agents/FolderPickerField";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { translateApiError } from "@/lib/api/errors";
import type { AgentCreate, AgentType } from "@/lib/api/agents";
import { agentTypeLabel } from "@/lib/agents/display";

const TYPES: AgentType[] = ["claude_code", "codex"];

interface Props {
  open: boolean;
  onToggle: () => void;
  /** Id the dialog footer's submit button targets via `form=`. */
  formId: string;
  /** Registers the agent; a rejection is shown inline and the form stays open. */
  onSubmit: (body: AgentCreate) => Promise<void>;
}

export function AgentManualAddForm({ open, onToggle, formId, onSubmit }: Props) {
  const { t } = useTranslation();
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [form, setForm] = useState<AgentCreate>({
    type: "claude_code",
    name: "",
    config_dir: null,
    description: null,
  });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    const name = (form.name ?? "").trim();
    try {
      // Name is optional — omit it when blank so the server derives a stable
      // per-type default (mirrors auto-detect naming).
      await onSubmit({ ...form, name: name || null });
    } catch (err) {
      // e.g. the AGENT_CONFIG_DIR_REGISTERED 409 — keep the form open for a retry.
      setErrorMsg(translateApiError(t, err));
    }
  };

  return (
    <section className="space-y-2 border-t pt-3">
      <button
        type="button"
        className="flex items-center gap-1.5 text-sm font-medium"
        aria-expanded={open}
        onClick={onToggle}
      >
        {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
        {t("agents.addManual")}
      </button>
      {open ? (
        <form id={formId} onSubmit={submit} className="space-y-3 pt-1">
          <div className="space-y-1.5">
            <Label htmlFor={`${formId}-type`}>{t("agents.type")}</Label>
            <Select
              value={form.type}
              onValueChange={(v) => setForm({ ...form, type: v as AgentType })}
            >
              <SelectTrigger id={`${formId}-type`} aria-label={t("agents.type")}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TYPES.map((ty) => (
                  <SelectItem key={ty} value={ty}>
                    {agentTypeLabel(ty)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={`${formId}-name`}>{t("agents.name")}</Label>
            <Input
              id={`${formId}-name`}
              placeholder={t("agents.namePlaceholder")}
              value={form.name ?? ""}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label>{t("agents.configDirOverride")}</Label>
            <FolderPickerField
              ariaLabel={t("agents.configDirOverride")}
              placeholder={t("agents.configDirPlaceholder")}
              value={form.config_dir ?? null}
              onChange={(p) => setForm({ ...form, config_dir: p })}
              clearable
            />
          </div>
          {errorMsg ? (
            <p role="alert" className="text-sm text-destructive">
              {errorMsg}
            </p>
          ) : null}
        </form>
      ) : null}
    </section>
  );
}
