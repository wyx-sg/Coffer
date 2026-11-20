// frontend/src/components/memory/MemoryDrawer.tsx
//
// One topic file, opened from the list (spec memory "Show and edit memory on
// the Memory page"): its type and last update under the title, what breaks the
// format when something does, then its memories as Markdown. The footer holds
// Edit (the whole file in a dialog) and Delete (asks first). Previous / next
// (↑ / ↓) step through the list.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Pencil, Trash2 } from "lucide-react";

import { Drawer } from "@/components/Drawer";
import { Markdown } from "@/components/Markdown";
import { MemoryEditDialog } from "@/components/memory/MemoryEditDialog";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { MemoryTopic } from "@/lib/api/memoryTypes";
import { useDeleteMemoryFile, useMemoryFile } from "@/lib/hooks/useMemory";
import { memoryCount } from "@/lib/memory/projects";

interface Props {
  /** The open file's list row, or `null` while the drawer is closed. */
  topic: MemoryTopic | null;
  onClose: () => void;
  onPrevious?: () => void;
  onNext?: () => void;
  hasPrevious?: boolean;
  hasNext?: boolean;
}

const TYPES = ["user", "feedback", "project"];

export function MemoryDrawer({ topic, onClose, ...stepping }: Props) {
  const { t } = useTranslation();
  const file = useMemoryFile(topic?.project ?? null, topic?.name ?? null);
  const remove = useDeleteMemoryFile();
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const facts = topic
    ? [
        t(`memory.type.${TYPES.includes(topic.type) ? topic.type : "none"}`),
        topic.updated,
        topic.name,
      ]
        .filter(Boolean)
        .join(" · ")
    : "";

  return (
    <>
      <Drawer
        open={topic !== null}
        onOpenChange={(open) => (open ? undefined : onClose())}
        title={topic?.title ?? ""}
        subtitle={topic ? <span className="font-sans">{facts}</span> : null}
        footerNote={topic ? t("memory.drawer.lines", { count: memoryCount(topic) }) : null}
        footer={
          topic ? (
            <>
              <Button variant="ghost" onClick={() => setDeleting(true)} disabled={!file.data}>
                <Trash2 aria-hidden />
                {t("memory.drawer.delete")}
              </Button>
              <Button variant="secondary" onClick={() => setEditing(true)} disabled={!file.data}>
                <Pencil aria-hidden />
                {t("memory.drawer.edit")}
              </Button>
            </>
          ) : null
        }
        {...stepping}
      >
        {topic ? (
          <div className="flex flex-col gap-4">
            {topic.problems.length > 0 ? (
              <Alert variant="warning">
                <AlertTriangle aria-hidden />
                <AlertTitle>{t("memory.problem.title")}</AlertTitle>
                <AlertDescription>
                  <ul className="list-disc pl-4">
                    {topic.problems.map((p) => (
                      <li key={p}>{t(`memory.problem.${p}`, { defaultValue: p })}</li>
                    ))}
                  </ul>
                  <p className="mt-1">{t("memory.problem.hint")}</p>
                </AlertDescription>
              </Alert>
            ) : null}
            <Markdown breaks>{topic.body}</Markdown>
          </div>
        ) : null}
      </Drawer>
      {topic && file.data ? (
        <MemoryEditDialog open={editing} onOpenChange={setEditing} file={file.data} />
      ) : null}
      {topic && file.data ? (
        <ConfirmDialog
          open={deleting}
          onOpenChange={(open) => {
            setDeleting(open);
            if (!open) remove.reset();
          }}
          title={t("memory.delete.title", { name: topic.name })}
          description={t("memory.delete.body")}
          confirmLabel={t("memory.drawer.delete")}
          variant="destructive"
          pending={remove.isPending}
          error={remove.error}
          errorTitle={t("memory.delete.failed", { name: topic.name })}
          onConfirm={() =>
            remove
              .mutateAsync({
                project: topic.project,
                name: topic.name,
                expected: file.data.digest,
              })
              .then(onClose)
          }
        />
      ) : null}
    </>
  );
}
