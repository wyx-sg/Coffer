import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { translateApiError } from "@/lib/api/errors";
import { useFetchSkill } from "@/lib/hooks/useSkills";

export function FetchForm(props: { onClose: () => void; onSuccess: () => void }) {
  const { t } = useTranslation();
  const fetchSkill = useFetchSkill();
  const [form, setForm] = useState({
    git_url: "",
    git_ref: "main",
    git_subpath: "",
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("skills.fetchTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            await fetchSkill.mutateAsync(form);
            props.onSuccess();
          }}
          className="space-y-3"
        >
          <label className="block text-sm">
            {t("skills.gitUrl")}
            <input
              className="mt-1 block w-full rounded border bg-background px-2 py-1 font-mono text-xs"
              required
              value={form.git_url}
              onChange={(e) => setForm({ ...form, git_url: e.target.value })}
              placeholder="https://github.com/owner/skills-repo"
            />
          </label>
          <label className="block text-sm">
            {t("skills.gitRef")}
            <input
              className="mt-1 block w-full rounded border bg-background px-2 py-1 font-mono text-xs"
              required
              value={form.git_ref}
              onChange={(e) => setForm({ ...form, git_ref: e.target.value })}
            />
          </label>
          <label className="block text-sm">
            {t("skills.gitSubpath")}
            <input
              className="mt-1 block w-full rounded border bg-background px-2 py-1 font-mono text-xs"
              value={form.git_subpath}
              onChange={(e) => setForm({ ...form, git_subpath: e.target.value })}
              placeholder="(optional)"
            />
          </label>
          {fetchSkill.error ? (
            <p className="text-sm text-destructive">{translateApiError(t, fetchSkill.error)}</p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={props.onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={fetchSkill.isPending}>
              {fetchSkill.isPending ? t("common.saving") : t("skills.fetch")}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
