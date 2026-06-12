// frontend/src/pages/settings/EmbeddingSettings.test.tsx
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  createMemoryRouter,
  Navigate,
  RouterProvider,
} from "react-router-dom";
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
  test("hides provider/model until embedding is enabled", () => {
    seed({ enabled: false });
    render(<EmbeddingSettings />, { wrapper: wrap });
    expect(screen.queryByLabelText(/^model$/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("switch"));
    expect(screen.getByLabelText(/^model$/i)).toBeInTheDocument();
  });

  test("saving PUTs the global embedding config", async () => {
    seed({ enabled: true, model: "bge-m3", dimensions: 1024 });
    render(<EmbeddingSettings />, { wrapper: wrap });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(mutate).toHaveBeenCalledWith(
        expect.objectContaining({ enabled: true, model: "bge-m3", dimensions: 1024 }),
      ),
    );
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
