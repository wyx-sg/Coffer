import { act, fireEvent, render, screen } from "@testing-library/react";
import { BrowserRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import { acceptance } from "@/test/acceptance";
import { useHistoryNav } from "@/lib/hooks/useHistoryNav";
import { useShellShortcuts } from "./useShellShortcuts";
import { WindowTitleStrip } from "./WindowTitleStrip";

const full = vi.hoisted(() => ({ value: false }));
vi.mock("@/lib/hooks/useWindowFullscreen", () => ({ useWindowFullscreen: () => full.value }));

function Where() {
  return <div data-testid="where">{useLocation().pathname}</div>;
}

function Go() {
  const navigate = useNavigate();
  return (
    <>
      <button onClick={() => navigate("/a")}>to-a</button>
      <button onClick={() => navigate("/b")}>to-b</button>
    </>
  );
}

function Strip({ collapsed = false }: { collapsed?: boolean }) {
  const history = useHistoryNav();
  useShellShortcuts({
    togglePalette: () => {},
    openSettings: () => {},
    goBack: history.goBack,
    goForward: history.goForward,
  });
  return (
    <WindowTitleStrip
      showToggle
      collapsed={collapsed}
      onToggle={() => {}}
      sidebarWidth={220}
      onBack={history.goBack}
      onForward={history.goForward}
    />
  );
}

function renderStrip(collapsed = false) {
  return render(
    <TooltipProvider>
      <BrowserRouter>
        <Strip collapsed={collapsed} />
        <Routes>
          <Route path="*" element={<Go />} />
        </Routes>
        <Where />
      </BrowserRouter>
    </TooltipProvider>,
  );
}

const wait = () => act(() => new Promise<void>((r) => setTimeout(r, 50)));

beforeEach(() => {
  full.value = false;
  window.history.replaceState(null, "", "/");
});

describe("WindowTitleStrip", () => {
  test("controls start right of the traffic lights, and at x 14 in full screen", () => {
    const first = renderStrip();
    expect(screen.getByTestId("title-controls").style.left).toBe("82px");
    first.unmount();
    full.value = true;
    renderStrip();
    expect(screen.getByTestId("title-controls").style.left).toBe("14px");
  });

  test("the sidebar's edge runs through the strip while it is expanded", () => {
    const first = renderStrip();
    expect(screen.getByTestId("title-sidebar-edge").style.left).toBe("220px");
    first.unmount();
    renderStrip(true);
    expect(screen.queryByTestId("title-sidebar-edge")).toBeNull();
  });

  acceptance(
    "web-ui",
    "the arrows in the title bar go back and forward through the app's history",
    async () => {
      renderStrip();
      const back = screen.getByRole("button", { name: "Back" });
      const forward = screen.getByRole("button", { name: "Forward" });
      // Nowhere to go yet: both are greyed out.
      expect(back).toBeDisabled();
      expect(forward).toBeDisabled();

      fireEvent.click(screen.getByText("to-a"));
      fireEvent.click(screen.getByText("to-b"));
      expect(back).toBeEnabled();
      expect(forward).toBeDisabled();

      fireEvent.click(back);
      await wait();
      expect(screen.getByTestId("where")).toHaveTextContent("/a");
      expect(forward).toBeEnabled();

      fireEvent.click(forward);
      await wait();
      expect(screen.getByTestId("where")).toHaveTextContent("/b");
      expect(forward).toBeDisabled();

      // The keyboard does the same, except while typing in a field.
      fireEvent.keyDown(window, { key: "[", metaKey: true });
      fireEvent.keyDown(window, { key: "[", ctrlKey: true });
      await wait();
      expect(screen.getByTestId("where")).toHaveTextContent("/a");
      fireEvent.keyDown(window, { key: "]", metaKey: true });
      fireEvent.keyDown(window, { key: "]", ctrlKey: true });
      await wait();
      expect(screen.getByTestId("where")).toHaveTextContent("/b");

      const input = document.createElement("input");
      document.body.appendChild(input);
      fireEvent.keyDown(input, { key: "[", metaKey: true, bubbles: true });
      fireEvent.keyDown(input, { key: "[", ctrlKey: true, bubbles: true });
      await wait();
      expect(screen.getByTestId("where")).toHaveTextContent("/b");
      input.remove();
    },
  );
});
