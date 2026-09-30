// src/components/agents/NewConfigFileDialog.tsx — a new file in a directory entry of the Config files tab (board 2.1.58).
//
// One Markdown file per entry (a Claude Code subagent). The name is a plain
// file name ending in .md; the file is created from a short template the user
// then edits, and saving goes through the same allowlisted write every edit uses.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { baseName } from "@/lib/agents/configFiles";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { ConfigFileInfo } from "@/lib/api/agents";
import { translateApiError } from "@/lib/api/errors";

const NAME = /^[A-Za-z0-9][A-Za-z0-9._-]*\.md$/;

/** The template a new file starts from: a subagent's front matter. */
export function newFileTemplate(relpath: string): string {
  const stem = relpath.replace(/\.md$/, "");
  return `---\nname: ${stem}\ndescription: \n---\n\n`;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  entry: ConfigFileInfo;
  onCreate: (relpath: string, content: string) => Promise<unknown>;
}

export function NewConfigFileDialog({ open, onOpenChange, entry, onCreate }: Props) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const trimmed = name.trim();
  const valid = NAME.test(trimmed);
  const exists = (entry.files ?? []).some((f) => f.relpath === trimmed);
  const dir = `${baseName(entry.path)}/`;

  const close = (next: boolean) => {
    if (!next) {
      setName("");
      setError(null);
    }
    onOpenChange(next);
  };

  const create = async () => {
    if (!valid || exists) return;
    setPending(true);
    setError(null);
    try {
      await onCreate(trimmed, newFileTemplate(trimmed));
      close(false);
    } catch (e) {
      setError(translateApiError(t, e));
    } finally {
      setPending(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-w-[440px]">
        <DialogHeader>
          <DialogTitle>{t("agents.configTab.newFileTitle", { dir })}</DialogTitle>
          <DialogDescription>{t("agents.configTab.newFileBody")}</DialogDescription>
        </DialogHeader>
        <label className="flex flex-col gap-1.5 text-xs font-label text-text">
          <span>
            {t("agents.configTab.newFileName")} <span aria-hidden>*</span>
          </span>
          <Input
            autoFocus
            value={name}
            placeholder="release-checker.md"
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void create();
            }}
            className="font-mono"
          />
        </label>
        <p className="text-2xs text-text-muted">
          {trimmed && !valid
            ? t("agents.configTab.newFileInvalid")
            : exists
              ? t("agents.configTab.newFileExists")
              : t("agents.configTab.newFileSavedAs", {
                  path: abbreviateHomePath(`${entry.path}/${trimmed || "…"}`),
                })}
        </p>
        {error ? <p className="text-xs text-danger">{error}</p> : null}
        <DialogFooter>
          <Button variant="ghost" onClick={() => close(false)}>
            {t("common.cancel")}
          </Button>
          <Button onClick={() => void create()} disabled={!valid || exists || pending}>
            {t("agents.configTab.newFileCreate")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
