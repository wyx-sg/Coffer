// src/components/custom-tools/ToolsTable.test.tsx — a group's Tools table: select-all and row boxes, the selection
// bar replacing the toolbar, bulk Turn off, and no All on / All off or "N of M on" on the title row.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { customToolsApi } from "@/lib/api/customTools";
import { ToolsTable } from "./ToolsTable";
import { makeGroup, makeTool } from "./testFixtures";

vi.mock("@/lib/api/customTools", () => ({
  customToolsApi: { updateTool: vi.fn() },
}));

const group = makeGroup({
  tools: [
    makeTool({ name: "get_invoice" }),
    makeTool({ name: "list_invoices" }),
    makeTool({ name: "void_invoice", enabled: false }),
  ],
});

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToolsTable
        group={group}
        rows={[]}
        showExposure={false}
        onOpenTool={vi.fn()}
        onAddRequest={vi.fn()}
      />
    </QueryClientProvider>,
  );
}

describe("ToolsTable", () => {
  beforeEach(() => {
    vi.mocked(customToolsApi.updateTool).mockReset();
    vi.mocked(customToolsApi.updateTool).mockResolvedValue(group);
  });

  test("has no All on / All off buttons and no count", () => {
    mount();
    expect(screen.queryByRole("button", { name: /all on|全部开启/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /all off|全部关闭/i })).toBeNull();
    expect(screen.queryByText(/of 3 on|个中已开启/)).toBeNull();
  });

  test("select-all shows the bar in place of the toolbar", () => {
    mount();
    expect(screen.getByRole("button", { name: /add request|添加请求/i })).toBeTruthy();
    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    expect(screen.getByRole("region", { name: "Selected tools" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /add request|添加请求/i })).toBeNull();
    expect(screen.getAllByRole("checkbox").every((c) => (c as HTMLInputElement).checked)).toBe(
      true,
    );
  });

  test("bulk Turn off switches only the tools that are on", async () => {
    mount();
    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    fireEvent.click(screen.getByRole("button", { name: "Turn off" }));
    await waitFor(() => expect(customToolsApi.updateTool).toHaveBeenCalledTimes(2));
    expect(customToolsApi.updateTool).toHaveBeenCalledWith("billing", "get_invoice", {
      enabled: false,
    });
    expect(customToolsApi.updateTool).not.toHaveBeenCalledWith(
      "billing",
      "void_invoice",
      expect.anything(),
    );
    await waitFor(() =>
      expect(screen.queryByRole("region", { name: "Selected tools" })).toBeNull(),
    );
  });
});
