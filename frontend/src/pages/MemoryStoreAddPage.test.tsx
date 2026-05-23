// frontend/src/pages/MemoryStoreAddPage.test.tsx — TEST26-014
//
// Form-render + submit-path coverage for the Add Memory Store page. The
// page calls `createMemoryStore` from kinds/memory/api; we mock the
// module so the form's wiring is verified without a real backend.

import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import type { PropsWithChildren } from "react";
import { MemoryStoreAddPage } from "./MemoryStoreAddPage";

vi.mock("@/kinds/memory/api", () => ({
  createMemoryStore: vi.fn(),
}));
const api = await import("@/kinds/memory/api");
const createMemoryStoreMock = vi.mocked(api.createMemoryStore);

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/add"]}>
        <Routes>
          <Route path="/add" element={children ?? ui} />
          <Route path="/resources" element={<div>resources-landing</div>} />
          <Route path="/resources/memory/:name" element={<div>memory-detail</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

afterEach(() => vi.clearAllMocks());

describe("MemoryStoreAddPage", () => {
  test("renders the form with default provider 'none' and hides LLM fields", () => {
    render(<MemoryStoreAddPage />, { wrapper: wrap(null) });
    expect(screen.getByLabelText(/^name$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/llm provider/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/llm model/i)).not.toBeInTheDocument();
  });

  test("revealing ollama provider shows the model + endpoint fields", () => {
    render(<MemoryStoreAddPage />, { wrapper: wrap(null) });
    const sel = screen.getByLabelText(/llm provider/i);
    fireEvent.change(sel, { target: { value: "ollama" } });
    expect(screen.getByLabelText(/llm model/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/ollama endpoint/i)).toBeInTheDocument();
    // openai-specific field is hidden under ollama.
    expect(screen.queryByLabelText(/keychain reference/i)).not.toBeInTheDocument();
  });

  test("revealing openai provider requires the keychain reference", () => {
    render(<MemoryStoreAddPage />, { wrapper: wrap(null) });
    fireEvent.change(screen.getByLabelText(/llm provider/i), {
      target: { value: "openai" },
    });
    expect(screen.getByLabelText(/keychain reference/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/ollama endpoint/i)).not.toBeInTheDocument();
  });

  test("submitting with provider=none calls createMemoryStore with the right payload", async () => {
    createMemoryStoreMock.mockResolvedValue({
      ref: "memory:prefs",
      kind: "memory",
      name: "prefs",
      description: null,
      config: {
        embedding_model: "BAAI/bge-small-en-v1.5",
        llm_provider: "none",
        llm_model: null,
        llm_endpoint: null,
        llm_credential_ref: null,
        max_memory_chars: 8192,
      },
      enabled: true,
      created_at: "2026-05-29T00:00:00Z",
      updated_at: "2026-05-29T00:00:00Z",
    });

    render(<MemoryStoreAddPage />, { wrapper: wrap(null) });
    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "prefs" } });
    fireEvent.click(screen.getByRole("button", { name: /create memory store/i }));

    await waitFor(() => expect(createMemoryStoreMock).toHaveBeenCalledOnce());
    const payload = createMemoryStoreMock.mock.calls[0][0];
    expect(payload.name).toBe("prefs");
    expect(payload.description).toBeNull();
    expect(payload.config.llm_provider).toBe("none");
    expect(payload.config.embedding_model).toBe("BAAI/bge-small-en-v1.5");
    expect(payload.config.max_memory_chars).toBe(8192);
  });

  test("surfaces a backend error message on submit failure", async () => {
    createMemoryStoreMock.mockRejectedValue(new Error("HTTP 409: name taken"));

    render(<MemoryStoreAddPage />, { wrapper: wrap(null) });
    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "dup" } });
    fireEvent.click(screen.getByRole("button", { name: /create memory store/i }));

    await waitFor(() => expect(screen.getByText(/HTTP 409: name taken/i)).toBeInTheDocument());
  });

  test("Back button navigates to /resources", () => {
    render(<MemoryStoreAddPage />, { wrapper: wrap(null) });
    fireEvent.click(screen.getByRole("button", { name: /back/i }));
    expect(screen.getByText("resources-landing")).toBeInTheDocument();
  });

  test("submit button is disabled while the request is pending", () => {
    // Returning a Promise that never resolves keeps `isPending` true.
    createMemoryStoreMock.mockImplementation(() => new Promise(() => {}));

    render(<MemoryStoreAddPage />, { wrapper: wrap(null) });
    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "p" } });
    fireEvent.click(screen.getByRole("button", { name: /create memory store/i }));
    // While pending, the button text switches to "Creating…" and is disabled.
    expect(screen.getByRole("button", { name: /creating/i })).toBeDisabled();
  });
});
