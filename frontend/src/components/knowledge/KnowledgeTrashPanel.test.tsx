// frontend/src/components/knowledge/KnowledgeTrashPanel.test.tsx
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { KnowledgeTrashPanel } from "./KnowledgeTrashPanel";
import type { KnowledgeItem } from "@/lib/api/knowledge";

const TRASHED: KnowledgeItem[] = [
  {
    ref: "doc:kb1:d9",
    type: "document",
    scopeId: "g",
    title: "trashed doc",
    preview: "",
    updatedAt: "t",
    kbName: "kb1",
    documentId: "d9",
    deletedAt: "2026-06-19T00:00:00Z",
  },
];

describe("KnowledgeTrashPanel", () => {
  test("lists trashed documents with Restore + Purge", () => {
    render(
      <KnowledgeTrashPanel
        open
        onOpenChange={() => {}}
        items={TRASHED}
        isLoading={false}
        isBusy={false}
        onRestore={() => {}}
        onPurge={() => {}}
      />,
    );
    expect(screen.getByText("trashed doc")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /restore/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /purge/i })).toBeInTheDocument();
  });

  test("restore and purge fire with the item", () => {
    const onRestore = vi.fn();
    const onPurge = vi.fn();
    render(
      <KnowledgeTrashPanel
        open
        onOpenChange={() => {}}
        items={TRASHED}
        isLoading={false}
        isBusy={false}
        onRestore={onRestore}
        onPurge={onPurge}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /restore/i }));
    fireEvent.click(screen.getByRole("button", { name: /purge/i }));
    expect(onRestore).toHaveBeenCalledWith(TRASHED[0]);
    expect(onPurge).toHaveBeenCalledWith(TRASHED[0]);
  });

  test("shows an empty state when the trash is empty", () => {
    render(
      <KnowledgeTrashPanel
        open
        onOpenChange={() => {}}
        items={[]}
        isLoading={false}
        isBusy={false}
        onRestore={() => {}}
        onPurge={() => {}}
      />,
    );
    expect(screen.getByText(/the trash is empty/i)).toBeInTheDocument();
  });
});
