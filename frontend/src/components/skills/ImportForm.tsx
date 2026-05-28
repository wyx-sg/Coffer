import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { translateApiError } from "@/lib/api/errors";
import { useImportSkill } from "@/lib/hooks/useSkills";

export function ImportForm(props: { onClose: () => void; onSuccess: () => void }) {
  const { t } = useTranslation();
  const importSkill = useImportSkill();
  const [path, setPath] = useState("");
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("skills.importTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            await importSkill.mutateAsync({ path });
            props.onSuccess();
          }}
          className="space-y-3"
        >
          <label className="block text-sm">
            {t("skills.path")}
            <input
              className="mt-1 block w-full rounded border bg-background px-2 py-1 font-mono text-xs"
              required
              value={path}
              onChange={(e) => setPath(e.target.value)}
              placeholder="/Users/me/.claude/skills/my-skill"
            />
          </label>
          {importSkill.error ? (
            <p className="text-sm text-destructive">{translateApiError(t, importSkill.error)}</p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={props.onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={importSkill.isPending}>
              {importSkill.isPending ? t("common.saving") : t("skills.import")}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
