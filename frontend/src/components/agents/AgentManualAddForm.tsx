// frontend/src/components/agents/AgentManualAddForm.tsx — spec 004.
// The "Add manually" disclosure + form inside the Add-agent dialog: agent type
// + optional name + config_dir picker. Self-contained — registers via
// useRegisterAgent, surfaces its own register error inline, and reports the new
// name up via onAdded so the parent dialog can show its result view. The folder
// the user picks IS the config dir; skills are delivered to `<config_dir>/skills`.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight } from "lucide-react";

import { FolderPickerField } from "@/components/agents/FolderPickerField";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";
import type { AgentCreate, AgentType } from "@/lib/api/agents";
import { useRegisterAgent } from "@/lib/hooks/useAgents";

const TYPES: AgentType[] = ["claude_code", "codex", "opencode", "hermes", "cursor"];

export function AgentManualAddForm({ onAdded }: { onAdded: (name: string) => void }) {
  const { t } = useTranslation();
  const register = useRegisterAgent();
  const [open, setOpen] = useState(false);
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
      await register.mutateAsync({ ...form, name: name || null });
      onAdded(name || form.type);
    } catch (err) {
      // Surface inline (e.g. the AGENT_CONFIG_DIR_REGISTERED 409) and keep the
      // form open for a retry.
      setErrorMsg(translateApiError(t, err));
    }
  };

  return (
    <section className="space-y-2 border-t pt-3">
      <button
        type="button"
        className="flex items-center gap-1.5 text-sm font-medium"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
        {t("agents.addManual")}
      </button>
      {open ? (
        <form onSubmit={submit} className="space-y-3 pt-1">
          <label className="block text-sm">
            {t("agents.type")}
            <select
              className="mt-1 block w-full rounded border bg-background px-2 py-1"
              value={form.type}
              onChange={(e) => setForm({ ...form, type: e.target.value as AgentType })}
            >
              {TYPES.map((ty) => (
                <option key={ty} value={ty}>
                  {ty}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            {t("agents.name")}
            <input
              className="mt-1 block w-full rounded border bg-background px-2 py-1"
              placeholder={t("agents.namePlaceholder")}
              value={form.name ?? ""}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </label>
          <div className="block text-sm">
            <span>{t("agents.configDirOverride")}</span>
            <div className="mt-1">
              <FolderPickerField
                ariaLabel={t("agents.configDirOverride")}
                placeholder={t("agents.configDirPlaceholder")}
                value={form.config_dir ?? null}
                onChange={(p) => setForm({ ...form, config_dir: p })}
                clearable
              />
            </div>
          </div>
          {errorMsg ? <p className="text-sm text-destructive">{errorMsg}</p> : null}
          <Button type="submit" disabled={register.isPending}>
            {register.isPending ? t("common.saving") : t("agents.register")}
          </Button>
        </form>
      ) : null}
    </section>
  );
}
