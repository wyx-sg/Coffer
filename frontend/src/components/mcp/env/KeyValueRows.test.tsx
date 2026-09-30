// src/components/mcp/env/KeyValueRows.test.tsx — the shared KEY / value rows
// with the stored-secret picker off (the Add form's mode).
import { useState } from "react";
import { expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import type { ParsedEnvVar } from "@/lib/mcp/pasteTypes";
import { KeyValueRows } from "../add/KeyValueRows";

vi.mock("@/lib/hooks/useSecretNames", () => ({
  useSecretNames: vi.fn(() => {
    throw new Error("the Add form must not load the Secrets list");
  }),
}));

function Harness({
  initial,
  seen,
}: {
  initial: ParsedEnvVar[];
  seen: (r: ParsedEnvVar[]) => void;
}) {
  const [rows, setRows] = useState(initial);
  return (
    <KeyValueRows
      idPrefix="t"
      label="Environment"
      keyPlaceholder="API_KEY"
      rows={rows}
      onChange={(next) => {
        seen(next);
        setRows(next);
      }}
    />
  );
}

test("each row is Secret or Plain; a Secret row takes a masked value", () => {
  const seen = vi.fn();
  render(<Harness initial={[{ key: "TOKEN", value: "", isSecret: true }]} seen={seen} />);
  const value = screen.getByLabelText("Value of TOKEN");
  expect(value).toHaveAttribute("type", "password");
  expect(
    screen.getByText("Enter the value of TOKEN; it goes to the keychain."),
  ).toBeInTheDocument();

  const kind = screen.getByRole("group", { name: "How TOKEN is kept" });
  fireEvent.click(within(kind).getByRole("button", { name: "Plain" }));
  expect(seen).toHaveBeenLastCalledWith([{ key: "TOKEN", value: "", isSecret: false }]);
  expect(screen.getByLabelText("Value of TOKEN")).not.toHaveAttribute("type", "password");
});

test("Add variable appends a Plain row; the section hint says where secrets live", () => {
  const seen = vi.fn();
  render(<Harness initial={[]} seen={seen} />);
  fireEvent.click(screen.getByRole("button", { name: /add variable/i }));
  expect(seen).toHaveBeenLastCalledWith([{ key: "", value: "", isSecret: false }]);
  expect(
    screen.getByText(
      "Secret values stay in Coffer's keychain; the agent's config never holds them.",
    ),
  ).toBeInTheDocument();
});
