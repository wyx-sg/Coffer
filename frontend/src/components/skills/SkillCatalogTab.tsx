// frontend/src/components/skills/SkillCatalogTab.tsx
// "Browse catalog" tab body for SkillAddDialog (FR-032/FR-033): search the
// bundled catalog and install an entry, which rides the validated+scanned fetch
// path. Kept as its own component to keep SkillAddDialog under the size cap.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { useCatalog, useInstallCatalogSkill } from "@/lib/hooks/useSkills";

export function SkillCatalogTab({
  onSuccess,
  onCancel,
}: {
  onSuccess: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const catalog = useCatalog(query);
  const install = useInstallCatalogSkill();

  return (
    <div className="space-y-3">
      <input
        className="block w-full rounded border bg-background px-2 py-1 text-sm"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={t("skills.catalog.searchPlaceholder")}
        aria-label={t("skills.catalog.searchPlaceholder")}
      />
      <ul className="max-h-72 space-y-2 overflow-y-auto">
        {(catalog.data ?? []).map((e) => (
          <li key={e.name} className="flex items-start justify-between gap-3 rounded border p-2">
            <div className="min-w-0">
              <div className="truncate text-sm font-medium">{e.name}</div>
              <div className="truncate text-xs text-muted-foreground">{e.description}</div>
              <div className="truncate text-xs text-muted-foreground">{e.publisher}</div>
            </div>
            <Button
              type="button"
              size="sm"
              disabled={install.isPending}
              onClick={async () => {
                try {
                  await install.mutateAsync(e.name);
                  onSuccess();
                } catch {
                  // Surfaced via the shared mutation error toast.
                }
              }}
            >
              {t("skills.catalog.install")}
            </Button>
          </li>
        ))}
        {catalog.data && catalog.data.length === 0 ? (
          <li className="text-sm text-muted-foreground">{t("skills.catalog.empty")}</li>
        ) : null}
      </ul>
      <div className="flex justify-end">
        <Button type="button" variant="outline" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
      </div>
    </div>
  );
}
