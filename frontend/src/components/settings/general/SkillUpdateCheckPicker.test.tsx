// frontend/src/components/settings/general/SkillUpdateCheckPicker.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

import i18n from "@/i18n";
import { acceptance } from "@/test/acceptance";
import { SkillUpdateCheckPicker } from "./SkillUpdateCheckPicker";

const api = vi.hoisted(() => ({ updateCheck: vi.fn(), setUpdateCheck: vi.fn() }));
vi.mock("@/lib/api/skills", () => ({ skillsApi: api }));

function renderPicker() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SkillUpdateCheckPicker />
    </QueryClientProvider>,
  );
}

describe("SkillUpdateCheckPicker", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    await i18n.changeLanguage("en");
    api.updateCheck.mockResolvedValue({ interval: "6h" });
  });

  acceptance("skill-manager", "the update check follows this machine's setting", async () => {
    api.setUpdateCheck.mockImplementation(async (interval: string) => ({ interval }));
    renderPicker();
    const select = screen.getByRole("combobox", { name: "Check skills for updates" });
    await waitFor(() => expect(select).not.toBeDisabled());
    fireEvent.keyDown(select, { key: "ArrowDown" });
    for (const [label, interval] of [
      ["Every day", "1d"],
      ["Only when I ask", "manual"],
    ] as const) {
      fireEvent.click(screen.getByRole("option", { name: label }));
      await waitFor(() => expect(api.setUpdateCheck).toHaveBeenLastCalledWith(interval));
      await waitFor(() => expect(select).toHaveTextContent(label));
      await waitFor(() => expect(select).not.toBeDisabled());
      fireEvent.keyDown(select, { key: "ArrowDown" });
    }
  });

  test("offers the four choices", async () => {
    renderPicker();
    const select = screen.getByRole("combobox", { name: "Check skills for updates" });
    await waitFor(() => expect(select).not.toBeDisabled());
    fireEvent.keyDown(select, { key: "ArrowDown" });
    for (const name of ["Every 6 hours", "Every day", "Every week", "Only when I ask"]) {
      expect(screen.getByRole("option", { name })).toBeInTheDocument();
    }
  });
});
