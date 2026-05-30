// frontend/src/components/agents/FolderPicker.tsx — spec 004 v2, FR-023.
// Hybrid skill-directory picker. In the packaged desktop app it uses the
// OS-native directory dialog; on the web it falls back to a daemon-backed
// folder browser (a browser can't read absolute paths, but the loopback
// daemon can). Both hand back a real absolute path.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { ChevronUp, Folder, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { translateApiError } from "@/lib/api/errors";
import { fsApi } from "@/lib/api/fs";
import { isTauri } from "@/lib/tauri";

/**
 * Open the Tauri OS-native directory dialog. The import specifier is held in a
 * variable + `@vite-ignore`d so the web build never tries to resolve the
 * desktop-only plugin; callers guard on `isTauri()` and fall back on throw.
 */
async function pickNative(defaultPath?: string): Promise<string | null> {
  const spec = "@tauri-apps/plugin-dialog";
  const mod = (await import(/* @vite-ignore */ spec)) as {
    open: (opts: {
      directory?: boolean;
      defaultPath?: string;
    }) => Promise<string | string[] | null>;
  };
  const picked = await mod.open({ directory: true, defaultPath });
  return typeof picked === "string" ? picked : null;
}

export function FolderPicker({
  value,
  onChange,
}: {
  value: string | null;
  onChange: (path: string) => void;
}) {
  const { t } = useTranslation();
  const [browserOpen, setBrowserOpen] = useState(false);

  const onBrowse = async () => {
    if (isTauri()) {
      try {
        const picked = await pickNative(value ?? undefined);
        if (picked) onChange(picked);
        return;
      } catch {
        // Native plugin unavailable — fall back to the daemon folder browser.
      }
    }
    setBrowserOpen(true);
  };

  return (
    <>
      <Button type="button" variant="outline" size="sm" onClick={onBrowse}>
        {t("agents.folderPicker.browse")}
      </Button>
      <FolderBrowserDialog
        open={browserOpen}
        startPath={value}
        onOpenChange={setBrowserOpen}
        onSelect={(p) => {
          onChange(p);
          setBrowserOpen(false);
        }}
      />
    </>
  );
}

function FolderBrowserDialog({
  open,
  startPath,
  onOpenChange,
  onSelect,
}: {
  open: boolean;
  startPath: string | null;
  onOpenChange: (open: boolean) => void;
  onSelect: (path: string) => void;
}) {
  const { t } = useTranslation();
  const [path, setPath] = useState<string | null>(startPath ?? null);

  // Reset to the field's current value each time the browser (re)opens.
  useEffect(() => {
    if (open) setPath(startPath ?? null);
  }, [open, startPath]);

  const browse = useQuery({
    queryKey: ["fs", "browse", path ?? "~"],
    queryFn: () => fsApi.browse(path),
    enabled: open,
  });
  const data = browse.data;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("agents.folderPicker.title")}</DialogTitle>
          <DialogDescription>{t("agents.folderPicker.subtitle")}</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={!data?.parent}
              onClick={() => data?.parent && setPath(data.parent)}
              aria-label={t("agents.folderPicker.up")}
            >
              <ChevronUp className="size-4" />
            </Button>
            <span className="truncate font-mono text-xs text-muted-foreground">
              {data?.path ?? t("common.loading")}
            </span>
          </div>
          <div className="h-64 overflow-y-auto rounded-md border">
            {browse.isPending ? (
              <div className="flex items-center gap-2 p-4 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" />
                {t("common.loading")}
              </div>
            ) : browse.isError ? (
              <p className="p-4 text-sm text-destructive">{translateApiError(t, browse.error)}</p>
            ) : (data?.entries.length ?? 0) === 0 ? (
              <p className="p-4 text-sm text-muted-foreground">
                {t("agents.folderPicker.emptyDir")}
              </p>
            ) : (
              <ul>
                {data!.entries.map((e) => (
                  <li key={e.path}>
                    <button
                      type="button"
                      onClick={() => setPath(e.path)}
                      className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent"
                    >
                      <Folder className="size-4 shrink-0 text-muted-foreground" />
                      <span className="truncate">{e.name}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button
            type="button"
            disabled={!data?.path}
            onClick={() => data?.path && onSelect(data.path)}
          >
            {t("agents.folderPicker.select")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
