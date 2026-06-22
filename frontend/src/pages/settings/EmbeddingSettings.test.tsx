// frontend/src/pages/settings/EmbeddingSettings.test.tsx
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, Navigate, RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { EmbeddingSettings } from "./EmbeddingSettings";

vi.mock("@/lib/hooks/useEmbeddingConfig", () => ({
  useEmbeddingConfig: vi.fn(),
  useUpdateEmbeddingConfig: vi.fn(),
}));
const hooks = await import("@/lib/hooks/useEmbeddingConfig");

function wrap({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const mutate = vi.fn();

afterEach(() => vi.clearAllMocks());

function seed(over: Partial<ReturnType<typeof hooks.useEmbeddingConfig>["data"]> = {}) {
  vi.mocked(hooks.useEmbeddingConfig).mockReturnValue({
    data: {
      enabled: false,
      provider: "local",
      model: "",
      base_url: null,
      credential_ref: null,
      dimensions: 768,
      default_chunk_size: 512,
      default_chunk_overlap: 64,
      updated_at: null,
      ...over,
    },
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof hooks.useEmbeddingConfig>);
  vi.mocked(hooks.useUpdateEmbeddingConfig).mockReturnValue({
    mutate,
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof hooks.useUpdateEmbeddingConfig>);
}

describe("EmbeddingSettings", () => {
  test("shows an Add button + empty hint when no model is configured", () => {
    seed({ model: "" });
    render(<EmbeddingSettings />, { wrapper: wrap });
    expect(screen.getByRole("button", { name: /add model/i })).toBeInTheDocument();
    expect(screen.getByText(/no embedding model configured/i)).toBeInTheDocument();
    // Model fields are not inline — they live in the dialog, opened on demand.
    expect(screen.queryByLabelText(/model id/i)).not.toBeInTheDocument();
  });

  test("opening Add reveals the model dialog with its fields", () => {
    seed({ model: "" });
    render(<EmbeddingSettings />, { wrapper: wrap });
    fireEvent.click(screen.getByRole("button", { name: /add model/i }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/add embedding model/i)).toBeInTheDocument();
    expect(within(dialog).getByLabelText(/model id/i)).toBeInTheDocument();
  });

  test("shows a summary row + Edit (no Add) once a model is set", () => {
    seed({ enabled: true, model: "bge-m3", dimensions: 1024 });
    render(<EmbeddingSettings />, { wrapper: wrap });
    expect(screen.getByText("bge-m3")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /edit/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /add model/i })).not.toBeInTheDocument();
  });

  test("auto-saves (no inline Save button) — toggling enable PUTs the config", () => {
    seed({ enabled: true, model: "bge-m3", dimensions: 1024 });
    render(<EmbeddingSettings />, { wrapper: wrap });
    // No inline Save button: the chunking fields persist on change/blur.
    expect(screen.queryByRole("button", { name: /^save$/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("switch"));
    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({ enabled: false, model: "bge-m3", dimensions: 1024 }),
    );
  });

  test("changing the model asks for confirmation before re-embedding", async () => {
    seed({ enabled: true, model: "bge-m3", dimensions: 1024 });
    render(<EmbeddingSettings />, { wrapper: wrap });
    fireEvent.click(screen.getByRole("button", { name: /edit/i }));

    const dialog = screen.getByRole("dialog");
    const input = within(dialog).getByLabelText(/model id/i);
    fireEvent.change(input, { target: { value: "text-embedding-3-small" } });
    fireEvent.click(within(dialog).getByRole("button", { name: /^save$/i }));

    // The change is held behind a confirmation, not persisted yet.
    expect(mutate).not.toHaveBeenCalled();
    const confirm = await screen.findByText(/change embedding model\?/i);
    expect(confirm).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /change & re-embed/i }));
    await waitFor(() =>
      expect(mutate).toHaveBeenCalledWith(
        expect.objectContaining({ model: "text-embedding-3-small" }),
      ),
    );
    // The confirmation closes once accepted.
    await waitFor(() =>
      expect(screen.queryByText(/change embedding model\?/i)).not.toBeInTheDocument(),
    );
  });

  test("changing only the dimensions also asks for confirmation", async () => {
    seed({ enabled: true, model: "bge-m3", dimensions: 1024 });
    render(<EmbeddingSettings />, { wrapper: wrap });
    fireEvent.click(screen.getByRole("button", { name: /edit/i }));

    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/dimensions/i), { target: { value: "512" } });
    fireEvent.click(within(dialog).getByRole("button", { name: /^save$/i }));

    expect(mutate).not.toHaveBeenCalled();
    expect(await screen.findByText(/change embedding model\?/i)).toBeInTheDocument();
  });
});

describe("legacy /settings/embedding redirect", () => {
  test("redirects the old embedding route to the merged Models page", async () => {
    const router = createMemoryRouter(
      [
        { path: "/settings/models", element: <div>models page</div> },
        {
          path: "/settings/embedding",
          element: <Navigate to="/settings/models" replace />,
        },
      ],
      { initialEntries: ["/settings/embedding"] },
    );
    render(<RouterProvider router={router} />);
    await waitFor(() => expect(screen.getByText("models page")).toBeInTheDocument());
    expect(router.state.location.pathname).toBe("/settings/models");
  });
});
