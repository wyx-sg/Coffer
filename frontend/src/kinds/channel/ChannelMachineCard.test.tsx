// frontend/src/kinds/channel/ChannelMachineCard.test.tsx
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { ChannelMachineCard } from "./ChannelMachineCard";
import type { SyncMachine } from "@/lib/hooks/useSync";

vi.mock("@/lib/hooks/useSync", () => ({ useSyncMachines: vi.fn() }));
vi.mock("@/lib/hooks/useChannels", () => ({ useUpdateChannel: vi.fn() }));
const sync = await import("@/lib/hooks/useSync");
const channels = await import("@/lib/hooks/useChannels");

const LOCAL: SyncMachine = {
  machine_id: "M-LOCAL",
  display_name: "studio",
  platform: "darwin",
  os_version: null,
  coffer_version: null,
  last_sync_at: null,
  is_local: true,
};
const OTHER: SyncMachine = {
  ...LOCAL,
  machine_id: "M-OTHER",
  display_name: "laptop",
  is_local: false,
};

const mutate = vi.fn();

function seed(machines: SyncMachine[]) {
  vi.mocked(sync.useSyncMachines).mockReturnValue({
    data: { machines },
  } as unknown as ReturnType<typeof sync.useSyncMachines>);
  vi.mocked(channels.useUpdateChannel).mockReturnValue({
    mutate,
    isPending: false,
  } as unknown as ReturnType<typeof channels.useUpdateChannel>);
}

describe("ChannelMachineCard", () => {
  test("unbound channel warns and offers to run here", () => {
    seed([LOCAL, OTHER]);
    render(<ChannelMachineCard name="tg" config={{ channel_type: "telegram" }} />);
    expect(screen.getByText(/not bound/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /run on this machine/i }));
    expect(mutate).toHaveBeenCalledWith({
      name: "tg",
      config: { channel_type: "telegram", runs_on: "M-LOCAL" },
      secrets: [],
    });
  });

  test("bound to this machine shows the badge and no rebind button", () => {
    seed([LOCAL, OTHER]);
    render(<ChannelMachineCard name="tg" config={{ runs_on: "M-LOCAL" }} />);
    expect(screen.getByText(/this machine/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run on this machine/i })).not.toBeInTheDocument();
  });

  test("bound elsewhere shows that machine's name and can rebind", () => {
    seed([LOCAL, OTHER]);
    render(<ChannelMachineCard name="tg" config={{ runs_on: "M-OTHER" }} />);
    expect(screen.getByText("laptop")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run on this machine/i })).toBeInTheDocument();
  });
});
