// frontend/src/components/agents/FolderPicker.tsx — spec agent-registry v2, FR-023.
// Skill-directory picker. The browser can't read absolute paths, so Browse asks
// the loopback daemon to open the host's OS-native directory dialog, and falls
// back to a daemon-backed in-app folder browser when this host has no native
// dialog tool. Either way it hands back a real absolute path.
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
    // Ask the daemon to open the OS-native dialog. Fall back to the in-app
    // browser only when this host has no native dialog tool.
    try {
      const res = await fsApi.pickFolder(value ?? undefined);
      if (res.available) {
        if (res.path) onChange(res.path);
        return; // native dialog handled it (picked or cancelled)
      }
    } catch {
      // Daemon picker errored — fall back to the in-app browser.
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
