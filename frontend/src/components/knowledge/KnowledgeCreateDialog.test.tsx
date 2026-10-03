// frontend/src/components/knowledge/KnowledgeCreateDialog.test.tsx
//
// The submit button shipped reading `t("common.create")` against a key that
// existed in neither locale, so the dialog rendered the literal string
// "common.create" where "Create" belonged. `locales.test.ts` could not catch
// it: it checks en/zh parity, and both were equally missing the key. So the
// assertion here is on the RENDERED label — the only place the mistake was
// visible — with the real locale bundles that `src/test/setup.ts` installs.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { KnowledgeCreateDialog } from "./KnowledgeCreateDialog";
import { ToastProvider } from "@/components/ui/toast";

vi.mock("@/lib/api/knowledge", () => ({
  createCollection: vi.fn(),
}));

const { createCollection } = await import("@/lib/api/knowledge");
const createCollectionMock = vi.mocked(createCollection);

afterEach(() => vi.clearAllMocks());

function renderDialog(onOpenChange = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter initialEntries={["/knowledge"]}>
          <Routes>
            <Route
              path="/knowledge"
              element={<KnowledgeCreateDialog open onOpenChange={onOpenChange} />}
            />
            <Route path="/knowledge/:uid" element={<p>opened the new collection</p>} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
  return onOpenChange;
}

describe("KnowledgeCreateDialog", () => {
  test("every label is translated — no raw i18n key reaches the screen", () => {
    renderDialog();

    // The regression: a missing key makes i18next echo the key itself.
    expect(screen.queryByText(/^[a-z][A-Za-z]*(\.[A-Za-z]+)+$/)).toBeNull();
    expect(screen.getByRole("button", { name: "Create collection" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });

  test("submitting sends the trimmed name, closes on success and opens the collection", async () => {
    createCollectionMock.mockResolvedValue({
      // The daemon mints the collection's identity; the dialog only ever sends
      // the name it was typed under.
      uid: "kn-9b04",
      name: "team-notes",
      description: "what we know",
      document_count: 0,
      pending_count: 0,
      folder_path: "/home/u/.coffer/knowledge/team-notes",
      updated_at: null,
    });
    const onOpenChange = renderDialog();

    fireEvent.change(screen.getByLabelText(/^name/i), { target: { value: "  team-notes  " } });
    fireEvent.change(screen.getByLabelText(/^what belongs in here/i), {
      target: { value: " what we know " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create collection" }));

    await waitFor(() =>
      expect(createCollectionMock).toHaveBeenCalledWith({
        name: "team-notes",
        description: "what we know",
      }),
    );
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(await screen.findByText("opened the new collection")).toBeInTheDocument();
  });

  test("a blank name or a blank description cannot be submitted", () => {
    renderDialog();
    expect(screen.getByRole("button", { name: "Create collection" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/^name/i), { target: { value: "team-notes" } });
    // A collection has no title: its description is what agents know it by,
    // so it is required too.
    expect(screen.getByRole("button", { name: "Create collection" })).toBeDisabled();
  });
});
