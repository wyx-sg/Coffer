// frontend/src/pages/settings/GeneralSettings.test.tsx
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import i18n from "@/i18n";
import { GeneralSettings } from "./GeneralSettings";
import { DataTable, type Column } from "@/components/DataTable";
import { acceptance } from "@/test/acceptance";

// The Speech-to-text section has its own tests (and its own daemon routes);
// stub it so these stay about the preferences this page owns, and need no
// query client.
vi.mock("./EngineSettings", () => ({
  EngineSettings: () => null,
}));

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

afterEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});

const STORE_KEY = "coffer.preferredEditor";

const editorSelect = () => screen.getByRole("combobox", { name: /open files with/i });
// Radix Select opens on keyboard in jsdom (pointer events are stubbed).
const openEditorPicker = () => fireEvent.keyDown(editorSelect(), { key: "ArrowDown" });
const pickOption = (name: RegExp | string) => fireEvent.click(screen.getByRole("option", { name }));
const customInput = () =>
  screen.getByRole("textbox", { name: /custom editor command/i }) as HTMLInputElement;

describe("GeneralSettings", () => {
  test("renders the default page-size control reflecting the stored preference", () => {
    localStorage.setItem("coffer.pageSize", "50");
    render(<GeneralSettings />);
    expect(screen.getAllByText(/rows per page/i)[0]).toBeInTheDocument();
    // The Select trigger shows the persisted value.
    expect(screen.getByRole("combobox", { name: /rows per page/i })).toHaveTextContent("50");
  });

  test("pickers are the shared Select and choices are segmented — no native <select>", () => {
    render(<GeneralSettings />);
    expect(document.querySelectorAll("select")).toHaveLength(0);
    expect(screen.getAllByRole("combobox")).toHaveLength(2);
    expect(screen.getByRole("group", { name: /^language$/i })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: /^theme$/i })).toBeInTheDocument();
  });

  test("the language choice switches the interface language at once", () => {
    render(<GeneralSettings />);
    const group = screen.getByRole("group", { name: /^language$/i });
    const english = within(group).getByRole("button", { name: "English" });
    expect(english).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(within(group).getByRole("button", { name: "中文" }));
    expect(i18n.language).toBe("zh");
    void i18n.changeLanguage("en");
  });
});

describe("GeneralSettings preferred editor", () => {
  test("picking a detected editor stores its launcher value", () => {
    render(<GeneralSettings />);
    openEditorPicker();
    pickOption("Cursor");
    expect(localStorage.getItem(STORE_KEY)).toBe("cursor");
    expect(editorSelect()).toHaveTextContent("Cursor");
    // A detected editor needs no free-text field.
    expect(screen.queryByRole("textbox", { name: /custom editor command/i })).toBeNull();
  });

  test("choosing system default clears the override", () => {
    localStorage.setItem(STORE_KEY, "code");
    render(<GeneralSettings />);
    expect(editorSelect()).toHaveTextContent("Visual Studio Code");
    openEditorPicker();
    pickOption(/system default/i);
    expect(localStorage.getItem(STORE_KEY)).toBeNull();
    expect(editorSelect()).toHaveTextContent(/system default/i);
  });

  test("Custom… reveals a text field whose value persists on blur", () => {
    render(<GeneralSettings />);
    openEditorPicker();
    pickOption(/custom/i);
    const input = customInput();
    fireEvent.change(input, { target: { value: "/Applications/Zed.app" } });
    fireEvent.blur(input);
    expect(localStorage.getItem(STORE_KEY)).toBe("/Applications/Zed.app");

    fireEvent.change(input, { target: { value: "" } });
    fireEvent.blur(input);
    expect(localStorage.getItem(STORE_KEY)).toBeNull();
  });

  test("a stored custom value (not in the picker) shows as Custom with the field open", () => {
    localStorage.setItem(STORE_KEY, "/opt/weird/editor");
    render(<GeneralSettings />);
    expect(editorSelect()).toHaveTextContent(/custom/i);
    expect(customInput().value).toBe("/opt/weird/editor");
  });
});

acceptance("web-ui", "general tab persists the preferred editor", () => {
  const { unmount } = render(<GeneralSettings />);

  // Choosing an application from the picker persists it.
  openEditorPicker();
  pickOption("Visual Studio Code");
  expect(localStorage.getItem("coffer.preferredEditor")).toBe("code");

  // Reloading the page shows the same persisted value in the picker.
  unmount();
  render(<GeneralSettings />);
  expect(editorSelect()).toHaveTextContent("Visual Studio Code");

  // Clearing the override restores the operating-system default (empty store).
  openEditorPicker();
  pickOption(/system default/i);
  expect(localStorage.getItem("coffer.preferredEditor")).toBeNull();
});

acceptance("web-ui", "the default page size seeds every list table", () => {
  type Row = { id: string; name: string };
  const rows: Row[] = Array.from({ length: 25 }, (_, i) => ({ id: String(i), name: `row-${i}` }));
  const cols: Column<Row>[] = [{ key: "name", header: "Name", cell: (r) => r.name }];
  render(
    <>
      <GeneralSettings />
      <DataTable rows={rows} columns={cols} rowKey={(r) => r.id} emptyMessage="none" />
    </>,
  );
  // The default of 20 rows per page: row-19 shows, row-20 is on page 2.
  expect(screen.getByText("row-19")).toBeInTheDocument();
  expect(screen.queryByText("row-20")).not.toBeInTheDocument();

  const pageSize = screen.getByRole("combobox", { name: /rows per page/i });
  fireEvent.keyDown(pageSize, { key: "ArrowDown" });
  fireEvent.click(screen.getByRole("option", { name: "10" }));

  expect(localStorage.getItem("coffer.pageSize")).toBe("10");
  expect(screen.getByText("row-9")).toBeInTheDocument();
  expect(screen.queryByText("row-10")).not.toBeInTheDocument();
});

acceptance("web-ui", "the General tab offers the theme choice", () => {
  localStorage.setItem("coffer.theme", "light");
  render(<GeneralSettings />);

  // One choice of three, with the current preference chosen.
  const group = screen.getByRole("group", { name: /^theme$/i });
  const buttons = within(group).getAllByRole("button");
  expect(buttons.map((b) => b.textContent).sort()).toEqual(["Dark", "Light", "System"]);
  expect(within(group).getByRole("button", { name: "Light" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  // Picking one applies it at once — there is no Save button.
  fireEvent.click(within(group).getByRole("button", { name: "Dark" }));
  expect(document.documentElement.dataset.theme).toBe("dark");
  expect(localStorage.getItem("coffer.theme")).toBe("dark");
  expect(within(group).getByRole("button", { name: "Dark" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(screen.queryByRole("button", { name: /save/i })).toBeNull();
});
