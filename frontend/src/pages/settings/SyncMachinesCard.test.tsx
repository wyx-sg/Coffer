// frontend/src/pages/settings/SyncMachinesCard.test.tsx
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { SyncMachinesCard } from "./SyncMachinesCard";
import type { SyncMachine } from "@/lib/hooks/useSync";

vi.mock("@/lib/hooks/useSync", () => ({
  useSyncMachines: vi.fn(),
  useRenameMachine: vi.fn(),
}));
const hooks = await import("@/lib/hooks/useSync");

function wrap({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const rename = vi.fn();

afterEach(() => vi.clearAllMocks());

const LOCAL: SyncMachine = {
  machine_id: "01AAAAAAAAAAAAAAAAAAAAAAAA",
  display_name: "studio",
  platform: "darwin",
  os_version: "25.5.0",
  coffer_version: "0.1.1",
  last_sync_at: "2026-07-10T12:00:00+00:00",
  is_local: true,
};

const OTHER: SyncMachine = {
  machine_id: "01BBBBBBBBBBBBBBBBBBBBBBBB",
  display_name: "laptop",
  platform: "darwin",
  os_version: "24.0.0",
  coffer_version: "0.1.1",
  last_sync_at: null,
  is_local: false,
};

function seed(machines: SyncMachine[]) {
  vi.mocked(hooks.useSyncMachines).mockReturnValue({
    data: { machines },
  } as unknown as ReturnType<typeof hooks.useSyncMachines>);
  vi.mocked(hooks.useRenameMachine).mockReturnValue({
    mutate: rename,
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof hooks.useRenameMachine>);
}

describe("SyncMachinesCard", () => {
  test("renders nothing when no machines are known", () => {
    seed([]);
    const { container } = render(<SyncMachinesCard />, { wrapper: wrap });
    expect(container).toBeEmptyDOMElement();
  });

  test("lists machines, badges the local one, shows never-synced for others", () => {
    seed([LOCAL, OTHER]);
    render(<SyncMachinesCard />, { wrapper: wrap });
    expect(screen.getByText(/this machine/i)).toBeInTheDocument();
    expect(screen.getByText("laptop")).toBeInTheDocument();
    expect(screen.getByText(/never synced/i)).toBeInTheDocument();
    // Local machine name is editable; the other is plain text.
    expect(screen.getByRole("textbox")).toHaveValue("studio");
  });

  test("renaming the local machine commits the trimmed name on blur", () => {
    seed([LOCAL, OTHER]);
    render(<SyncMachinesCard />, { wrapper: wrap });
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "  workshop  " } });
    fireEvent.blur(input);
    expect(rename).toHaveBeenCalledWith("workshop");
  });

  test("blank rename reverts instead of saving", () => {
    seed([LOCAL]);
    render(<SyncMachinesCard />, { wrapper: wrap });
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "   " } });
    fireEvent.blur(input);
    expect(rename).not.toHaveBeenCalled();
    expect(input).toHaveValue("studio");
  });
});
