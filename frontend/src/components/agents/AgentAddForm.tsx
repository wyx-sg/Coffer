import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { translateApiError } from "@/lib/api/errors";
import type { AgentCreate, AgentType } from "@/lib/api/agents";
import { useRegisterAgent } from "@/lib/hooks/useAgents";

const TYPES: AgentType[] = ["claude_code", "claude_desktop", "cursor", "codex_cli"];

export function AgentAddForm(props: { onClose: () => void; onCreated: () => void }) {
  const { t } = useTranslation();
  const register = useRegisterAgent();
  const [form, setForm] = useState<AgentCreate>({
    type: "cursor",
    name: "",
    skill_dir: null,
    description: null,
  });
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    await register.mutateAsync(form);
    props.onCreated();
  };
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("agents.addTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-3">
          <label className="block text-sm">
            {t("agents.type")}
            <select
              className="mt-1 block w-full rounded border bg-background px-2 py-1"
              value={form.type}
              onChange={(e) => setForm({ ...form, type: e.target.value as AgentType })}
            >
              {TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            {t("agents.name")}
            <input
              className="mt-1 block w-full rounded border bg-background px-2 py-1"
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </label>
          <label className="block text-sm">
            {t("agents.skillDirOverride")}
            <input
              className="mt-1 block w-full rounded border bg-background px-2 py-1 font-mono text-xs"
              placeholder={t("agents.skillDirPlaceholder")}
              value={form.skill_dir ?? ""}
              onChange={(e) => setForm({ ...form, skill_dir: e.target.value || null })}
            />
          </label>
          {register.error ? (
            <p className="text-sm text-destructive">{translateApiError(t, register.error)}</p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={props.onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={register.isPending}>
              {register.isPending ? t("common.saving") : t("agents.register")}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
