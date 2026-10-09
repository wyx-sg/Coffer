// src/components/settings/about/UninstallSection.test.tsx
//
// Settings › About › Uninstall against a stand-in for the desktop shell: the
// dialog says what goes and what stays, keeps the data unless asked, warns and
// offers a backup when asked, and hands the choice to the shell. In a browser
// the section shows the command.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { acceptance } from "@/test/acceptance";
import type { UninstallReport } from "@/lib/shellUninstall";

const shell = vi.hoisted(() => ({
  inApp: true,
  uninstall: vi.fn<(deleteData: boolean) => Promise<UninstallReport>>(),
}));

vi.mock("@/lib/shellUninstall", () => ({
  uninstallAvailable: () => shell.inApp,
  uninstallCoffer: (deleteData: boolean) => shell.uninstall(deleteData),
}));

const { UninstallSection } = await import("./UninstallSection");

function renderSection(url = "/settings/about") {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <UninstallSection />
    </MemoryRouter>,
  );
}

const REPORT: UninstallReport = {
  ok: true,
  deletes_data: false,
  steps: [
    { key: "agent_connections", outcome: "done", detail: "Claude Code" },
    { key: "login_job", outcome: "nothing", detail: "" },
  ],
};

describe("UninstallSection", () => {
  beforeEach(() => {
    shell.inApp = true;
    shell.uninstall.mockReset();
    shell.uninstall.mockResolvedValue(REPORT);
  });

  acceptance(
    "web-ui",
    "the uninstall dialog names what it removes and keeps the data by default",
    async () => {
      renderSection();
      fireEvent.click(screen.getByRole("button", { name: "Uninstall Coffer…" }));
      const dialog = await screen.findByRole("dialog");
      expect(dialog).toHaveTextContent(/MCP entry, memory hook/);
      expect(dialog).toHaveTextContent(/~\/\.coffer: your vault/);
      expect(screen.getByRole("checkbox", { name: /delete my data/i })).not.toBeChecked();
      fireEvent.click(screen.getByRole("button", { name: "Uninstall" }));
      await waitFor(() => expect(shell.uninstall).toHaveBeenCalledWith(false));
      expect(await screen.findByText("Coffer is uninstalled")).toBeInTheDocument();
      expect(screen.getByTestId("uninstall-steps")).toHaveTextContent(/Agents disconnected/);
    },
  );

  acceptance("web-ui", "ticking delete my data warns and offers a backup", async () => {
    renderSection();
    fireEvent.click(screen.getByRole("button", { name: "Uninstall Coffer…" }));
    fireEvent.click(await screen.findByRole("checkbox", { name: /delete my data/i }));
    expect(screen.getByText("This cannot be undone")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back up the master key/i })).toHaveAttribute(
      "href",
      "/settings/security?backup=1",
    );
    expect(screen.getByRole("dialog")).toHaveTextContent(
      /Nothing\. ~\/\.coffer and the master key/,
    );
    fireEvent.click(screen.getByRole("button", { name: "Uninstall and delete data" }));
    await waitFor(() => expect(shell.uninstall).toHaveBeenCalledWith(true));
  });

  acceptance("web-ui", "about in a browser shows the uninstall command", () => {
    shell.inApp = false;
    renderSection();
    expect(screen.getByText("coffer uninstall")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Uninstall Coffer…" })).not.toBeInTheDocument();
  });

  test("coffer uninstall --delete-data opens the dialog with the box ticked", async () => {
    renderSection("/settings/about?uninstall=1&delete=1");
    expect(await screen.findByRole("checkbox", { name: /delete my data/i })).toBeChecked();
  });

  test("a failed uninstall stays in the dialog", async () => {
    shell.uninstall.mockRejectedValue(new Error("the daemon is not running"));
    renderSection();
    fireEvent.click(screen.getByRole("button", { name: "Uninstall Coffer…" }));
    fireEvent.click(await screen.findByRole("button", { name: "Uninstall" }));
    expect(await screen.findByText(/the daemon is not running/)).toBeInTheDocument();
    expect(screen.queryByText("Coffer is uninstalled")).not.toBeInTheDocument();
  });
});
