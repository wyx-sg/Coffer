// src/components/custom-tools/ToolResponseTab.test.tsx — the Response tab chooses between the group's rules and
// rules of this tool only, and the form sends that choice as `response_rules`.
import { useState } from "react";
import { describe, expect, test } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import type { ResponseRule } from "@/lib/api/customTools";
import { acceptance } from "@/test/acceptance";
import { makeTool } from "./testFixtures";
import { ToolResponseTab } from "./ToolResponseTab";
import { formOf, toolOf, type ToolForm } from "./toolForm";

const GROUP_RULE: ResponseRule = {
  source: "header",
  name: "x-result-code",
  ok_values: ["OK"],
  missing: "ok",
  message: { source: "header", name: "x-result-text" },
};

let latest: ToolForm;

function Harness({ initial, groupRules }: { initial: ToolForm; groupRules: ResponseRule[] }) {
  const [form, setForm] = useState(initial);
  latest = form;
  return <ToolResponseTab form={form} onChange={setForm} groupRules={groupRules} />;
}

describe("ToolResponseTab", () => {
  test("follows the group by default and shows its rules compactly", () => {
    render(<Harness initial={formOf(makeTool())} groupRules={[GROUP_RULE]} />);
    expect(screen.getByLabelText("Use the group's rules")).toBeChecked();
    expect(
      screen.getByText(
        "header x-result-code ∈ OK · missing: success · message: header x-result-text",
      ),
    ).toBeInTheDocument();
    expect(toolOf(latest).response_rules).toBeNull();
  });

  test("says HTTP status only when the group has no rules", () => {
    render(<Harness initial={formOf(makeTool())} groupRules={[]} />);
    expect(screen.getByText("HTTP status only")).toBeInTheDocument();
  });

  acceptance("web-ui", "a tool follows its group's response rules or sets its own", () => {
    render(<Harness initial={formOf(makeTool())} groupRules={[GROUP_RULE]} />);
    fireEvent.click(screen.getByLabelText("Rules for this tool only"));
    expect(toolOf(latest).response_rules).toEqual([GROUP_RULE]);
    fireEvent.change(screen.getByLabelText("Success values"), { target: { value: "OK, DONE" } });
    expect(toolOf(latest).response_rules?.[0].ok_values).toEqual(["OK", "DONE"]);
    fireEvent.click(screen.getByRole("button", { name: "Remove rule" }));
    expect(toolOf(latest).response_rules).toEqual([]);
  });

  test("switching back follows the group again", () => {
    render(
      <Harness initial={formOf(makeTool({ response_rules: [] }))} groupRules={[GROUP_RULE]} />,
    );
    expect(screen.getByLabelText("Rules for this tool only")).toBeChecked();
    fireEvent.click(screen.getByLabelText("Use the group's rules"));
    expect(toolOf(latest).response_rules).toBeNull();
  });
});
