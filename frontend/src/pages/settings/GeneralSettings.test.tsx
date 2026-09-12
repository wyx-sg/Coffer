// frontend/src/pages/settings/GeneralSettings.test.tsx
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GeneralSettings } from "./GeneralSettings";
import { acceptance } from "@/test/acceptance";

// The picker lists editors the daemon detected as installed; stub that out so
// these tests drive a fixed set without a live daemon.
vi.mock("@/lib/hooks/useEditors", () => ({
  useDetectedEditors: () => ({
    data: [
      { label: "Visual Studio Code", value: "code" },
      { label: "Cursor", value: "cursor" },
    ],
  }),
}));

// The tab also carries the daemon-port card, which asks the daemon where it is
// serving from. These tests are about the display preferences, so answer that
// one route with a fixed port and leave the card's own behaviour to
// DaemonPortCard.test.tsx.
beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            configured_port: null,
            effective_port: 8003,
            restart_required: false,
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
    ),
  );
});

afterEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

/** The tab needs a query client now that one of its cards talks to the daemon. */
function renderGeneral() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <GeneralSettings />
    </QueryClientProvider>,
  );
}

const STORE_KEY = "coffer.preferredEditor";

const editorInput = () =>
  screen.getByRole("textbox", { name: /preferred editor/i }) as HTMLInputElement;
const openEditorPicker = () =>
  fireEvent.click(screen.getByRole("button", { name: /choose editor/i }));

describe("GeneralSettings", () => {
  test("renders the daemon-port card below the display preferences", async () => {
    renderGeneral();
    expect(await screen.findByText("http://127.0.0.1:8003")).toBeInTheDocument();
  });

  test("renders the default page-size control reflecting the stored preference", () => {
    localStorage.setItem("coffer.pageSize", "50");
    renderGeneral();
    expect(screen.getByText(/default rows per page/i)).toBeInTheDocument();
    // The Select trigger shows the persisted value.
    expect(screen.getByRole("combobox", { name: /default rows per page/i })).toHaveTextContent(
      "50",
    );
  });
});

describe("GeneralSettings preferred editor", () => {
  test("picking a detected editor fills the field with its launcher value", () => {
    renderGeneral();
    openEditorPicker();
    fireEvent.click(screen.getByRole("button", { name: "Cursor" }));
    expect(localStorage.getItem(STORE_KEY)).toBe("cursor");
    // The value lands in the editable field in place — no separate text box.
    expect(editorInput().value).toBe("cursor");
  });

  test("choosing system default clears the override", () => {
    localStorage.setItem(STORE_KEY, "code");
    renderGeneral();
    expect(editorInput().value).toBe("code");
    openEditorPicker();
    fireEvent.click(screen.getByRole("button", { name: /system default/i }));
    expect(localStorage.getItem(STORE_KEY)).toBeNull();
    expect(editorInput().value).toBe("");
  });

  test("a custom editor is typed straight into the field and persists", () => {
    renderGeneral();
    const input = editorInput();
    fireEvent.change(input, { target: { value: "/Applications/Zed.app" } });
    fireEvent.blur(input);
    expect(localStorage.getItem(STORE_KEY)).toBe("/Applications/Zed.app");

    fireEvent.change(input, { target: { value: "" } });
    fireEvent.blur(input);
    expect(localStorage.getItem(STORE_KEY)).toBeNull();
  });

  test("a stored custom value (not in the picker) shows in the field on load", () => {
    localStorage.setItem(STORE_KEY, "/opt/weird/editor");
    renderGeneral();
    expect(editorInput().value).toBe("/opt/weird/editor");
  });
});

acceptance("ui-shell", "general tab persists the preferred editor", () => {
  const { unmount } = renderGeneral();

  // Choosing an application from the picker persists it.
  fireEvent.click(screen.getByRole("button", { name: /choose editor/i }));
  fireEvent.click(screen.getByRole("button", { name: "Visual Studio Code" }));
  expect(localStorage.getItem("coffer.preferredEditor")).toBe("code");

  // Reloading the page shows the same persisted value in the field.
  unmount();
  renderGeneral();
  expect(editorInput().value).toBe("code");

  // Clearing the override restores the operating-system default (empty store).
  fireEvent.click(screen.getByRole("button", { name: /choose editor/i }));
  fireEvent.click(screen.getByRole("button", { name: /system default/i }));
  expect(localStorage.getItem("coffer.preferredEditor")).toBeNull();
});
