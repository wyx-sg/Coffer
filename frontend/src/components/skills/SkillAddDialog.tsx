// frontend/src/components/skills/SkillAddDialog.tsx
// One combined "Add skill" dialog with two tabs: "Local folder" imports an
// AgentSkills-standard folder from disk; "From Git" fetches one from a public
// Git URL. Each tab body owns its own form + mutation and surfaces its own
// inline error. On success the skills query is invalidated and the dialog
// closes. This replaces the old inline ImportForm / FetchForm cards.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { translateApiError } from "@/lib/api/errors";
import { useFetchSkill, useImportSkill } from "@/lib/hooks/useSkills";

export function SkillAddDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: () => void;
}) {
  const { t } = useTranslation();

  const close = () => {
    onCreated();
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("skills.add")}</DialogTitle>
          <DialogDescription>{t("skills.addSubtitle")}</DialogDescription>
        </DialogHeader>
        <Tabs defaultValue="local">
          <TabsList>
            <TabsTrigger value="local">{t("skills.add.tabs.local")}</TabsTrigger>
            <TabsTrigger value="git">{t("skills.add.tabs.git")}</TabsTrigger>
          </TabsList>
          <TabsContent value="local" className="pt-4">
            <LocalImportTab onSuccess={close} onCancel={() => onOpenChange(false)} />
          </TabsContent>
          <TabsContent value="git" className="pt-4">
            <GitFetchTab onSuccess={close} onCancel={() => onOpenChange(false)} />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

function LocalImportTab({ onSuccess, onCancel }: { onSuccess: () => void; onCancel: () => void }) {
  const { t } = useTranslation();
  const importSkill = useImportSkill();
  const [path, setPath] = useState("");
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await importSkill.mutateAsync({ path });
          onSuccess();
        } catch {
          // Surfaced inline via importSkill.error below.
        }
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
        <Button type="button" variant="outline" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={importSkill.isPending}>
          {importSkill.isPending ? t("common.saving") : t("skills.import")}
        </Button>
      </div>
    </form>
  );
}

function GitFetchTab({ onSuccess, onCancel }: { onSuccess: () => void; onCancel: () => void }) {
  const { t } = useTranslation();
  const fetchSkill = useFetchSkill();
  const [form, setForm] = useState({ git_url: "", git_ref: "main", git_subpath: "" });
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await fetchSkill.mutateAsync(form);
          onSuccess();
        } catch {
          // Surfaced inline via fetchSkill.error below.
        }
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
        <Button type="button" variant="outline" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={fetchSkill.isPending}>
          {fetchSkill.isPending ? t("common.saving") : t("skills.fetch")}
        </Button>
      </div>
    </form>
  );
}
