// frontend/src/pages/SkillsPage.tsx — spec 004 surface.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { FetchForm } from "@/components/skills/FetchForm";
import { ImportForm } from "@/components/skills/ImportForm";
import { SkillTable } from "@/components/skills/SkillTable";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { translateApiError } from "@/lib/api/errors";
import { useSkills, useVerifySkills } from "@/lib/hooks/useSkills";

export function SkillsPage() {
  const { t } = useTranslation();
  const { data: skills, isPending, error, refetch } = useSkills();
  const verify = useVerifySkills();
  const [mode, setMode] = useState<null | "import" | "fetch">(null);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t("skills.title")}</h1>
          <p className="text-sm text-muted-foreground">{t("skills.subtitle")}</p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={async () => {
              const report = await verify.mutateAsync();
              if (report.entries.length === 0) {
                window.alert(t("skills.verifyOk"));
              } else {
                window.alert(t("skills.verifyDrift", { count: report.entries.length }));
              }
            }}
            disabled={verify.isPending}
          >
            {t("skills.verify")}
          </Button>
          <Button variant="outline" onClick={() => setMode("fetch")}>
            {t("skills.fetch")}
          </Button>
          <Button onClick={() => setMode("import")}>{t("skills.import")}</Button>
        </div>
      </div>

      {mode === "import" ? (
        <ImportForm
          onClose={() => setMode(null)}
          onSuccess={() => {
            void refetch();
            setMode(null);
          }}
        />
      ) : null}
      {mode === "fetch" ? (
        <FetchForm
          onClose={() => setMode(null)}
          onSuccess={() => {
            void refetch();
            setMode(null);
          }}
        />
      ) : null}

      {isPending ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            {t("common.loading")}
          </CardContent>
        </Card>
      ) : error ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-destructive">{t("skills.loadFailed")}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{translateApiError(t, error)}</p>
          </CardContent>
        </Card>
      ) : (skills ?? []).length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            {t("skills.empty")}
          </CardContent>
        </Card>
      ) : (
        <SkillTable skills={skills ?? []} />
      )}
    </div>
  );
}
