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
        <KnowledgeCreateDialog open onOpenChange={onOpenChange} />
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
    expect(screen.getByRole("button", { name: "Create" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });

  test("submitting sends the trimmed name and closes on success", async () => {
    createCollectionMock.mockResolvedValue({
      // The daemon mints the collection's identity; the dialog only ever sends
      // the name it was typed under.
      uid: "kn-9b04",
      name: "team-notes",
      description: "what we know",
      document_count: 0,
      pending_count: 0,
    });
    const onOpenChange = renderDialog();

    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: "  team-notes  " } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() =>
      expect(createCollectionMock).toHaveBeenCalledWith({
        name: "team-notes",
        description: null,
      }),
    );
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  test("a blank name cannot be submitted", () => {
    renderDialog();
    expect(screen.getByRole("button", { name: "Create" })).toBeDisabled();
  });
});
