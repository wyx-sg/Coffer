// frontend/src/components/memory/MemoryDrawer.tsx
//
// One memory, opened from the list (spec memory "Manage memory sync in the web
// UI and on the command line"): its type, origin and last change under the
// title, then where each agent holds it and its text (MemoryContent). Only the
// body scrolls, so a long memory reads in place, and the drawer's own Maximize
// gives it the width of the page. The memory is edited in the agent's own
// memory, never here; previous / next (↑ / ↓) step through the list.
import { useTranslation } from "react-i18next";

import { Drawer } from "@/components/Drawer";
import { MemoryContent } from "@/components/memory/MemoryContent";
import type { HubEntry } from "@/lib/api/memoryTypes";
import { useMemoryFacts } from "@/components/memory/useMemoryFacts";

interface Props {
  /** The open memory's list row, or `null` while the drawer is closed. */
  entry: HubEntry | null;
  machine: string;
  onClose: () => void;
  onPrevious?: () => void;
  onNext?: () => void;
  hasPrevious?: boolean;
  hasNext?: boolean;
}

export function MemoryDrawer({ entry, machine, onClose, ...stepping }: Props) {
  const { t } = useTranslation();
  const facts = useMemoryFacts(entry, machine);

  return (
    <Drawer
      open={entry !== null}
      onOpenChange={(open) => (open ? undefined : onClose())}
      title={entry?.title ?? ""}
      subtitle={entry ? <span className="font-sans">{facts}</span> : null}
      footerNote={t("memory.drawer.editHint")}
      {...stepping}
    >
      {entry ? <MemoryContent id={entry.id} title={entry.title} /> : null}
    </Drawer>
  );
}
