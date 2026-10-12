// src/components/custom-tools/BodyField.test.tsx — the body template's JSON editor: a template saved on one line opens
// laid out, its holes are not JSON mistakes, and a real mistake names its line.
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { acceptance } from "@/test/acceptance";
import { BodyField } from "./ToolRequestFields";
import { formOf } from "./toolForm";
import { makeTool } from "./testFixtures";

function form(body: string) {
  return formOf(makeTool({ method: "POST", body_template: body }));
}

describe("BodyField", () => {
  acceptance(
    "web-ui",
    "a one-line body template opens laid out and its holes are not errors",
    () => {
      const { container, unmount } = render(
        <BodyField form={form('{"ids":{ids},"region":{region},"flag":111}')} onChange={vi.fn()} />,
      );
      const lines = [...container.querySelectorAll(".cm-line")].map((l) => l.textContent);
      expect(lines).toEqual([
        "{",
        '  "ids": {ids},',
        '  "region": {region},',
        '  "flag": 111',
        "}",
      ]);
      expect(container.querySelectorAll(".cm-hole")).toHaveLength(2);
      expect(screen.queryByRole("alert")).toBeNull();
      expect(screen.getByRole("button", { name: "Format" })).toBeDisabled();
      unmount();

      render(<BodyField form={form('{\n  "a": 1,\n  "b":\n}')} onChange={vi.fn()} />);
      expect(screen.getByRole("alert")).toHaveTextContent(/near line 4/);
    },
  );

  it("formats a template written on several lines when asked", () => {
    const onChange = vi.fn();
    render(<BodyField form={form('{"a":\n{a}}')} onChange={onChange} />);
    screen.getByRole("button", { name: "Format" }).click();
    expect(onChange.mock.calls[0][0].body).toBe('{\n  "a": {a}\n}');
  });
});
