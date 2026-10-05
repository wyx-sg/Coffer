// frontend/src/pages/settings/GeneralSettings.test.tsx
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import i18n from "@/i18n";
import { GeneralSettings } from "./GeneralSettings";
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

// Likewise the terminals the daemon detected, and the managed agents the hand-off agent is chosen among.
vi.mock("@/lib/hooks/useTerminals", () => ({
  useDetectedTerminals: () => ({
    data: [
      { label: "Terminal", value: "terminal" },
      { label: "iTerm", value: "iterm" },
    ],
  }),
}));
// The skill-update-check row reads and writes the daemon; stub it like the others.
vi.mock("@/lib/hooks/useSkills", () => ({
  useSkillUpdateCheck: () => ({ data: { interval: "6h" } }),
  useSetSkillUpdateCheck: () => ({ mutate: vi.fn(), isPending: false }),
}));
const providers = vi.hoisted(() => ({
  agents: [] as { agent_key: string; display_name: string; available: boolean }[],
}));
vi.mock("@/lib/hooks/useAgentProviders", () => ({
  useAgentProviders: () => ({ data: providers.agents }),
}));
const BOTH_AGENTS = [
  { agent_key: "claude_code", display_name: "Claude Code", available: true },
  { agent_key: "codex", display_name: "Codex", available: true },
];

afterEach(() => {
  providers.agents = [];
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
  test("pickers are the shared Select and choices are segmented — no native <select>", () => {
    render(<GeneralSettings />);
    expect(document.querySelectorAll("select")).toHaveLength(0);
    expect(screen.getAllByRole("combobox")).toHaveLength(3);
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

const TERMINAL_KEY = "coffer.preferredTerminal";
const terminalSelect = () => screen.getByRole("combobox", { name: /preferred terminal/i });
const openTerminalPicker = () => fireEvent.keyDown(terminalSelect(), { key: "ArrowDown" });
const templateInput = () =>
  screen.getByRole("textbox", { name: /custom terminal command/i }) as HTMLInputElement;

describe("GeneralSettings preferred terminal", () => {
  test("picking a detected terminal stores its launcher value", () => {
    render(<GeneralSettings />);
    expect(terminalSelect()).toHaveTextContent("System terminal");
    openTerminalPicker();
    pickOption("iTerm");
    expect(localStorage.getItem(TERMINAL_KEY)).toBe("iterm");
    expect(terminalSelect()).toHaveTextContent("iTerm");
    expect(screen.queryByRole("textbox", { name: /custom terminal command/i })).toBeNull();
  });

  acceptance("web-ui", "general tab persists the preferred terminal", () => {
    const { unmount } = render(<GeneralSettings />);

    // A detected terminal persists across a reload.
    openTerminalPicker();
    pickOption("iTerm");
    unmount();
    const second = render(<GeneralSettings />);
    expect(terminalSelect()).toHaveTextContent("iTerm");

    // So does a custom template.
    openTerminalPicker();
    pickOption(/custom/i);
    fireEvent.change(templateInput(), { target: { value: "kitty sh -lc {command}" } });
    fireEvent.blur(templateInput());
    expect(localStorage.getItem(TERMINAL_KEY)).toBe("kitty sh -lc {command}");
    second.unmount();
    render(<GeneralSettings />);
    expect(terminalSelect()).toHaveTextContent(/custom/i);
    expect(templateInput().value).toBe("kitty sh -lc {command}");

    // Clearing the override restores the system terminal (empty store).
    openTerminalPicker();
    pickOption(/system terminal/i);
    expect(localStorage.getItem(TERMINAL_KEY)).toBeNull();
    expect(terminalSelect()).toHaveTextContent("System terminal");
  });

  acceptance("web-ui", "a custom terminal template must hold the command", () => {
    localStorage.setItem(TERMINAL_KEY, "iterm");
    render(<GeneralSettings />);
    openTerminalPicker();
    pickOption(/custom/i);
    // The hint names both placeholders.
    expect(screen.getByText(/\{cwd\}.*\{command\}/)).toBeInTheDocument();
    fireEvent.change(templateInput(), { target: { value: "kitty --directory {cwd}" } });
    fireEvent.blur(templateInput());
    expect(screen.getByRole("alert")).toHaveTextContent("The template needs {command}.");
    // Not saved: the previous value stands.
    expect(localStorage.getItem(TERMINAL_KEY)).toBe("iterm");

    fireEvent.change(templateInput(), { target: { value: "kitty --directory {cwd} {command}" } });
    fireEvent.blur(templateInput());
    expect(screen.queryByRole("alert")).toBeNull();
    expect(localStorage.getItem(TERMINAL_KEY)).toBe("kitty --directory {cwd} {command}");
  });
});

describe("GeneralSettings hand-off agent", () => {
  const agentSelect = () => screen.getByRole("combobox", { name: /hand-off agent/i });

  acceptance("web-ui", "general tab persists the hand-off agent", () => {
    providers.agents = BOTH_AGENTS;
    const { unmount } = render(<GeneralSettings />);
    // With none stored, the first managed agent is the hand-off agent.
    expect(agentSelect()).toHaveTextContent("Claude Code");
    fireEvent.keyDown(agentSelect(), { key: "ArrowDown" });
    pickOption("Codex");
    expect(localStorage.getItem("coffer.handoffAgent")).toBe("codex");

    unmount();
    render(<GeneralSettings />);
    expect(agentSelect()).toHaveTextContent("Codex");
  });

  test("a stored agent that is not managed reads as the first managed one", () => {
    providers.agents = [BOTH_AGENTS[0]];
    localStorage.setItem("coffer.handoffAgent", "codex");
    render(<GeneralSettings />);
    expect(agentSelect()).toHaveTextContent("Claude Code");
  });

  test("with no managed agent the setting offers nothing and says why", () => {
    render(<GeneralSettings />);
    expect(screen.queryByRole("combobox", { name: /hand-off agent/i })).toBeNull();
    expect(screen.getByText(/Install Claude Code or Codex to hand work off/)).toBeInTheDocument();
  });
});
