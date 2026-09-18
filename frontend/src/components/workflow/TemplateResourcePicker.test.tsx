// frontend/src/components/workflow/TemplateResourcePicker.test.tsx
//
// A template may name a skill or an agent the vault no longer has. The picker
// has to show it as what it is — a stale value, still selected, marked gone —
// rather than rendering blank, which would read as "no skill" and hide the
// reason the save is about to be refused.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { TemplateResourcePicker } from "./TemplateResourcePicker";
import { TooltipProvider } from "@/components/ui/tooltip";

function mount(value: string | null, onChange = vi.fn()) {
  render(
    <TooltipProvider>
      <TemplateResourcePicker
        id="pick"
        label="Skill"
        options={["coffer-writing-td", "coffer-submitting-review"]}
        value={value}
        onChange={onChange}
        noneLabel="No skill"
        path="stages[0].nodes[0].skill"
        refusal={null}
      />
    </TooltipProvider>,
  );
  return onChange;
}

describe("TemplateResourcePicker", () => {
  afterEach(() => vi.clearAllMocks());

  test("a registered value is shown as itself", () => {
    mount("coffer-writing-td");
    expect(screen.getByLabelText("Skill")).toHaveTextContent("coffer-writing-td");
  });

  test("null reads as the explicit 'nothing bound' option", () => {
    mount(null);
    expect(screen.getByLabelText("Skill")).toHaveTextContent("No skill");
  });

  test("a value the vault no longer has stays visible, marked as gone", async () => {
    mount("deleted-skill");
    expect(screen.getByLabelText("Skill")).toHaveTextContent(
      "deleted-skill — no longer registered",
    );
    // …and it is still in the list, so it can be replaced rather than only read.
    fireEvent.click(screen.getByLabelText("Skill"));
    expect(
      await screen.findByRole("option", { name: "deleted-skill — no longer registered" }),
    ).toBeInTheDocument();
  });

  test("choosing the empty option reports null, not a sentinel string", async () => {
    const onChange = mount("coffer-writing-td");
    fireEvent.click(screen.getByLabelText("Skill"));
    fireEvent.click(await screen.findByRole("option", { name: "No skill" }));
    expect(onChange).toHaveBeenCalledWith(null);
  });
});
