// frontend/src/components/agents/AgentManualAddForm.tsx — spec 004.
// The "Add manually" disclosure + form inside the Add-agent dialog: agent type
// + optional name + skill_dir picker. Self-contained — registers via
// useRegisterAgent, surfaces its own register error inline, and reports the new
// name up via onAdded so the parent dialog can show its result view.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight } from "lucide-react";

import { FolderPicker } from "@/components/agents/FolderPicker";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";
import type { AgentCreate, AgentType } from "@/lib/api/agents";
import { useRegisterAgent } from "@/lib/hooks/useAgents";

const TYPES: AgentType[] = ["claude_code", "codex"];

export function AgentManualAddForm({ onAdded }: { onAdded: (name: string) => void }) {
  const { t } = useTranslation();
  const register = useRegisterAgent();
  const [open, setOpen] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [form, setForm] = useState<AgentCreate>({
    type: "claude_code",
    name: "",
    skill_dir: null,
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
            <span>{t("agents.skillDirOverride")}</span>
            <div className="mt-1 flex gap-2">
              <input
                aria-label={t("agents.skillDirOverride")}
                className="block w-full rounded border bg-background px-2 py-1 font-mono text-xs"
                placeholder={t("agents.skillDirPlaceholder")}
                value={form.skill_dir ?? ""}
                onChange={(e) => setForm({ ...form, skill_dir: e.target.value || null })}
              />
              <FolderPicker
                value={form.skill_dir ?? null}
                onChange={(p) => setForm({ ...form, skill_dir: p })}
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
