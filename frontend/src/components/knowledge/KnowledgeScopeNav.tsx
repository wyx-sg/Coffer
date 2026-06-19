// frontend/src/components/knowledge/KnowledgeScopeNav.tsx
// The primary axis of the unified 知识 surface (ADR-030): 全局 (global) + one
// entry per project, shown by its readable directory name. Selecting a scope is
// navigation (a route param), so the chosen scope survives reload / deep-link.
import { useTranslation } from "react-i18next";
import { Globe, FolderGit2 } from "lucide-react";

import { cn } from "@/lib/utils";
import type { KnowledgeScope } from "@/lib/api/knowledge";

interface Props {
  scopes: KnowledgeScope[];
  selectedId: string | undefined;
  onSelect: (scope: KnowledgeScope) => void;
}

export function KnowledgeScopeNav({ scopes, selectedId, onSelect }: Props) {
  const { t } = useTranslation();
  return (
    <nav className="space-y-1" aria-label={t("knowledge.scope.aria")}>
      <p className="px-2 pb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {t("knowledge.scope.heading")}
      </p>
      {scopes.map((s) => {
        const isGlobal = s.kind === "global";
        const Icon = isGlobal ? Globe : FolderGit2;
        const label = isGlobal ? t("knowledge.scope.global") : s.label;
        const active = s.id === selectedId;
        return (
          <button
            key={s.id}
            type="button"
            onClick={() => onSelect(s)}
            className={cn(
              "flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm transition-colors",
              active
                ? "bg-primary/10 text-primary"
                : "text-foreground/80 hover:bg-secondary hover:text-foreground",
            )}
            aria-current={active ? "true" : undefined}
          >
            <Icon className="size-4 shrink-0" strokeWidth={1.75} />
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium">{label}</span>
              {s.projectRoot ? (
                <span className="block truncate font-mono text-xs text-muted-foreground">
                  {s.projectRoot}
                </span>
              ) : null}
            </span>
          </button>
        );
      })}
    </nav>
  );
}
