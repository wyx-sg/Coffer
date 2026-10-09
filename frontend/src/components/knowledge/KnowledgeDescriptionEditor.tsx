// frontend/src/components/knowledge/KnowledgeDescriptionEditor.tsx
//
// A collection's description edited in place (spec knowledge "Name a
// collection by its folder and edit its description in place"): a textarea
// where blur or ⌘Enter saves, Esc cancels, and the success toast offers Undo.
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { CollectionOut } from "@/lib/api/knowledge";
import { useDescribeCollection } from "@/lib/hooks/useKnowledge";

/** The description as a textarea: blur or ⌘Enter saves, Esc cancels. An empty
 *  description is never saved — leaving it blank keeps the old one. */
export function KnowledgeDescriptionEditor({
  collection,
  onDone,
}: {
  collection: CollectionOut;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const describe = useDescribeCollection(collection.uid);
  const [value, setValue] = useState(collection.description);
  // One decision per editing session: Esc must not be followed by a blur-save.
  const settled = useRef(false);
  const text = value.trim();

  const save = () => {
    if (settled.current || describe.isPending) return;
    if (!text || text === collection.description) {
      settled.current = true;
      onDone();
      return;
    }
    const previous = collection.description;
    describe.mutate(text, {
      onSuccess: () => {
        settled.current = true;
        onDone();
        toast.success(t("knowledge.collection.descriptionSaved"), {
          // Undo is the same describe mutation with the old text; a collection
          // that had no description has nothing to go back to.
          undo: previous
            ? () =>
                void describe
                  .mutateAsync(previous)
                  .catch(() => toast.error(t("knowledge.collection.descriptionUndoFailed")))
            : undefined,
        });
      },
    });
  };

  return (
    <div className="flex flex-col gap-2">
      <Textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        aria-label={t("knowledge.collection.descriptionLabel")}
        autoFocus
        onBlur={save}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
            e.preventDefault();
            save();
          } else if (e.key === "Escape") {
            e.preventDefault();
            settled.current = true;
            onDone();
          }
        }}
      />
      {describe.error ? (
        <p role="alert" className="text-sm text-danger">
          {translateApiError(t, describe.error)}
        </p>
      ) : null}
    </div>
  );
}
