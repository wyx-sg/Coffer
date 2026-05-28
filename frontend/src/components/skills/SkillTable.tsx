import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { SkillOut } from "@/lib/api/skills";
import { useRemoveSkill } from "@/lib/hooks/useSkills";

export function SkillTable({ skills }: { skills: SkillOut[] }) {
  const { t } = useTranslation();
  const remove = useRemoveSkill();
  return (
    <Card>
      <CardContent className="p-0">
        <table className="w-full text-sm">
          <thead className="border-b bg-muted/40">
            <tr className="text-left">
              <th className="px-4 py-2">{t("skills.name")}</th>
              <th className="px-4 py-2">{t("skills.source")}</th>
              <th className="px-4 py-2">{t("skills.bindings")}</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {skills.map((s) => (
              <tr key={s.name} className="border-b last:border-0">
                <td className="px-4 py-2 font-medium">{s.name}</td>
                <td className="px-4 py-2 text-muted-foreground">{s.source.type}</td>
                <td className="px-4 py-2 text-xs">
                  {s.bindings.length === 0
                    ? "—"
                    : s.bindings.map((b) => `${b.agent_name}${b.enabled ? "+" : "-"}`).join(", ")}
                </td>
                <td className="px-4 py-2 text-right">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      if (window.confirm(t("skills.removeConfirm", { name: s.name }))) {
                        remove.mutate(s.name);
                      }
                    }}
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
  );
}
