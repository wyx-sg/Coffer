// frontend/src/components/resource/EditTitleDialog.test.tsx
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { EditTitleDialog } from "./EditTitleDialog";
import { ResourceLabel } from "./ResourceLabel";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));
const { getApiClient } = await import("@/lib/api/client");

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

afterEach(() => vi.clearAllMocks());

describe("EditTitleDialog", () => {
  test("a renamable kind gets no fixed-name field and saves the title by uid", async () => {
    const patch = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    vi.mocked(getApiClient).mockReturnValue({ PATCH: patch } as unknown as ReturnType<
      typeof getApiClient
    >);
    render(wrap(<EditTitleDialog kind="knowledge" resource={{ uid: "u-kb", name: "team" }} />));

    fireEvent.click(screen.getByRole("button", { name: /edit title/i }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).queryByText("Fixed name")).not.toBeInTheDocument();
    expect(within(dialog).queryByText(/cannot change after registration/i)).not.toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText("Title"), { target: { value: "Team notes" } });
    fireEvent.click(within(dialog).getByRole("button", { name: /save/i }));

    await waitFor(() => expect(patch).toHaveBeenCalled());
    expect(patch.mock.calls[0][1]).toMatchObject({
      params: { path: { uid: "u-kb" } },
      body: { title: "Team notes" },
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  test("a refused title stays open with the error beside the field", async () => {
    const patch = vi.fn().mockResolvedValue({
      data: undefined,
      error: { error: { code: "VALIDATION_ERROR", message: "title too long" } },
    });
    vi.mocked(getApiClient).mockReturnValue({ PATCH: patch } as unknown as ReturnType<
      typeof getApiClient
    >);
    render(wrap(<EditTitleDialog kind="memory" resource={{ uid: "u-p", name: "global" }} />));
    fireEvent.click(screen.getByRole("button", { name: /edit title/i }));
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});

describe("ResourceLabel", () => {
  test("shows the title with the name beside it, or the name alone", () => {
    const { rerender } = render(
      <ResourceLabel resource={{ name: "srch", title: "Team search" }} />,
    );
    expect(screen.getByText("Team search")).toBeInTheDocument();
    expect(screen.getByText("srch")).toHaveAttribute("data-slot", "resource-name");

    rerender(<ResourceLabel resource={{ name: "srch", title: "   " }} />);
    expect(screen.getByText("srch")).not.toHaveAttribute("data-slot");
    expect(screen.queryByText("Team search")).not.toBeInTheDocument();
  });
});
