// frontend/src/kinds/knowledge/KnowledgeDetailHeader.tsx
//
// Header for one knowledge scope: a back link to the list, the scope's
// readable name + rename pencil, and the project path underneath. Two buttons
// carry the actions a person actually reaches for — Upload and Tidy; Settings,
// Check sources and Reindex live behind the overflow (⋯) menu. The only status
// shown is the degraded-documents warning, and only when there is one: chunk
// counts, byte sizes and index modes are internal mechanics, and the note /
// document counts are already the tree headers one tab down.
// Presentational — the page owns the data and the action triggers.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowLeft,
  FileSearch,
  MoreHorizontal,
  Pencil,
  RefreshCw,
  Settings as SettingsIcon,
  Sparkles,
  TriangleAlert,
  Upload,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { scopeDisplayName, type ScopeOut } from "./api";

interface Props {
  scope: string;
  scopeResource: ScopeOut | undefined;
  /** Documents indexed keyword-only because the embedder was unavailable. */
  degradedDocuments: number;
  isReindexPending: boolean;
  isUploadPending: boolean;
  isTidyPending: boolean;
  checkingSources: boolean;
  onRename: () => void;
  onOpenSettings: () => void;
  onCheckSources: () => void;
  onReindex: () => void;
  onUpload: () => void;
  onTidy: () => void;
}

export function KnowledgeDetailHeader({
  scope,
  scopeResource,
  degradedDocuments,
  isReindexPending,
  isUploadPending,
  isTidyPending,
  checkingSources,
  onRename,
  onOpenSettings,
  onCheckSources,
  onReindex,
  onUpload,
  onTidy,
}: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  // Readable identity: a user-set label, else the project_root basename, else
  // the scope's own (already readable) name — never the opaque project-<ULID>
  // as the title. While loading, show the raw scope name.
  const displayName = scopeResource
    ? (scopeDisplayName(scopeResource) ?? t("knowledge.unnamedScope"))
    : scope;
  const projectRoot = scopeResource?.project_root ?? null;
  const hasScope = Boolean(scopeResource);

  // One row of the overflow menu; closing on select keeps the popover from
  // hanging open over the dialog an item opens.
  const menuItem = (
    label: string,
    icon: React.ReactNode,
    onSelect: () => void,
    disabled = false,
  ) => (
    <button
      type="button"
      role="menuitem"
      disabled={disabled}
      onClick={() => {
        setMenuOpen(false);
        onSelect();
      }}
      className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-secondary hover:text-foreground disabled:pointer-events-none disabled:opacity-50"
    >
      {icon}
      {label}
    </button>
  );

  return (
    <header className="space-y-2">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => navigate("/knowledge")}
        className="-ml-2 text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="mr-1.5 size-4" /> {t("knowledge.detail.back")}
      </Button>

      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="font-serif text-3xl tracking-tight">{displayName}</h1>
          <Button
            variant="ghost"
            size="sm"
            className="-ml-1 text-muted-foreground hover:text-foreground"
            onClick={onRename}
            disabled={!hasScope}
            aria-label={t("knowledge.rename.title")}
          >
            <Pencil className="size-4" />
          </Button>
          {degradedDocuments > 0 ? (
            <span className="inline-flex items-center gap-1 rounded-sm border border-border px-2 py-0.5 text-xs text-status-warn">
              <TriangleAlert className="size-3" />
              {t("knowledge.detail.degradedBadge", { count: degradedDocuments })}
            </span>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onTidy}
            disabled={isTidyPending || !hasScope}
          >
            <Sparkles className="mr-1.5 size-3.5" /> {t("knowledge.detail.tidy")}
          </Button>
          <Button size="sm" onClick={onUpload} disabled={isUploadPending}>
            <Upload className="mr-1.5 size-3.5" /> {t("knowledge.detail.upload")}
          </Button>
          <Popover open={menuOpen} onOpenChange={setMenuOpen}>
            <PopoverTrigger asChild>
              <Button variant="ghost" size="sm" aria-label={t("knowledge.detail.moreActions")}>
                <MoreHorizontal className="size-4" />
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" role="menu" className="w-56 p-1">
              {menuItem(
                t("knowledge.detail.settings"),
                <SettingsIcon className="size-3.5" />,
                onOpenSettings,
                !hasScope,
              )}
              {menuItem(
                t("knowledge.detail.checkSources"),
                <FileSearch className="size-3.5" />,
                onCheckSources,
                checkingSources || !hasScope,
              )}
              {menuItem(
                t("knowledge.detail.reindex"),
                <RefreshCw className="size-3.5" />,
                onReindex,
                isReindexPending,
              )}
            </PopoverContent>
          </Popover>
        </div>
      </div>

      {projectRoot ? (
        <p className="truncate font-mono text-xs text-muted-foreground">{projectRoot}</p>
      ) : null}
    </header>
  );
}
