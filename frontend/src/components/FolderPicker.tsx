// frontend/src/components/FolderPicker.tsx — spec agent-registry "Offer a
// folder picker for a custom config directory".
// Skill-directory picker. The browser can't read absolute paths, so Browse asks
// the loopback daemon to open the host's OS-native directory dialog, and falls
// back to a daemon-backed in-app folder browser when this host has no native
// dialog tool. Either way it hands back a real absolute path.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronUp, Folder } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { translateApiError } from "@/lib/api/errors";
import { useFsActions } from "@/lib/fsActions";
import { useFsBrowse } from "@/lib/hooks/useFsBrowse";

export function FolderPicker({
  value,
  onChange,
  label,
}: {
  value: string | null;
  onChange: (path: string) => void;
  /** The button's text; "Browse…" when not given. */
  label?: string;
}) {
  const { t } = useTranslation();
  const [browserOpen, setBrowserOpen] = useState(false);
  const fs = useFsActions();

  const onBrowse = async () => {
    // Ask the daemon to open the OS-native dialog. Fall back to the in-app
    // browser only when this host has no native dialog tool.
    try {
      const res = await fs.pickFolder(value ?? undefined);
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
      <Button type="button" variant="outline" className="shrink-0" onClick={onBrowse}>
        {label ?? t("picker.browse")}
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

  const browse = useFsBrowse(path, { enabled: open });
  const data = browse.data;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("folderPicker.title")}</DialogTitle>
          <DialogDescription>{t("folderPicker.subtitle")}</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              disabled={!data?.parent}
              onClick={() => data?.parent && setPath(data.parent)}
              aria-label={t("folderPicker.up")}
            >
              <ChevronUp aria-hidden />
            </Button>
            <span className="truncate font-mono text-xs text-muted-foreground">
              {data?.path ?? t("common.loading")}
            </span>
          </div>
          <div className="h-64 overflow-y-auto rounded-lg border border-border">
            {browse.isPending ? (
              <div className="flex items-center gap-2 p-4 text-sm text-text-muted">
                <Spinner />
                {t("common.loading")}
              </div>
            ) : browse.isError ? (
              <p className="p-4 text-sm text-destructive">{translateApiError(t, browse.error)}</p>
            ) : (data?.entries.length ?? 0) === 0 ? (
              <p className="p-4 text-sm text-muted-foreground">{t("folderPicker.emptyDir")}</p>
            ) : (
              <ul>
                {data!.entries.map((e) => (
                  <li key={e.path}>
                    <button
                      type="button"
                      onClick={() => setPath(e.path)}
                      className="flex h-control-md w-full items-center gap-2 px-3 text-left text-sm transition-colors duration-fast hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus-ring"
                    >
                      <Folder className="size-3.5 shrink-0 text-text-subtle" aria-hidden />
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
            {t("folderPicker.select")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
