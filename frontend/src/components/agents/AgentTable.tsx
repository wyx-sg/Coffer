import { useState } from "react";
import { useTranslation } from "react-i18next";

import { AgentEditForm } from "@/components/agents/AgentEditForm";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { AgentOut } from "@/lib/api/agents";
import { useRemoveAgent } from "@/lib/hooks/useAgents";

export function AgentTable({ agents }: { agents: AgentOut[] }) {
  const { t } = useTranslation();
  const remove = useRemoveAgent();
  // Track which row is currently being edited (by name — unique within
  // kind=agent). `null` means no edit panel is open.
  const [editingName, setEditingName] = useState<string | null>(null);
  const editing = agents.find((a) => a.name === editingName) ?? null;
  return (
    <div className="space-y-4">
      {editing ? (
        <AgentEditForm
          agent={editing}
          onClose={() => setEditingName(null)}
          onSaved={() => setEditingName(null)}
        />
      ) : null}
      <Card>
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/40">
              <tr className="text-left">
                <th className="px-4 py-2">{t("agents.name")}</th>
                <th className="px-4 py-2">{t("agents.type")}</th>
                <th className="px-4 py-2">{t("agents.skillDir")}</th>
                <th className="px-4 py-2">{t("agents.auto")}</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {agents.map((a) => (
                <tr key={a.name} className="border-b last:border-0">
                  <td className="px-4 py-2 font-medium">{a.name}</td>
                  <td className="px-4 py-2 text-muted-foreground">{a.type}</td>
                  <td className="px-4 py-2 font-mono text-xs">{a.skill_dir}</td>
                  <td className="px-4 py-2">{a.auto_detected ? "✓" : ""}</td>
                  <td className="px-4 py-2 text-right">
                    <Button variant="ghost" size="sm" onClick={() => setEditingName(a.name)}>
                      {t("agents.edit")}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        if (window.confirm(t("agents.removeConfirm", { name: a.name }))) {
                          remove.mutate(a.name);
                        }
                      }}
                      disabled={remove.isPending}
                    >
                      {t("common.delete")}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
