// src/components/custom-tools/ToolArgumentsField.test.tsx — each argument says where the request uses it; an
// argument used nowhere and a hole with no argument are flagged with their fix; query rows follow the path.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { acceptance } from "@/test/acceptance";
import { argumentUses } from "@/lib/customTools/requestParts";
import { argsFromSchema } from "@/lib/customTools/schemaArgs";
import { ToolArgumentsField } from "./ToolArgumentsField";
import { ToolQueryField } from "./ToolQueryField";

const args = argsFromSchema({
  type: "object",
  properties: { query: { type: "string" }, status: { type: "string", enum: ["active"] } },
  required: ["query"],
});

describe("ToolArgumentsField", () => {
  acceptance("web-ui", "an argument the request never uses is flagged with its fix", () => {
    const onChange = vi.fn();
    const onAddToQuery = vi.fn();
    const uses = argumentUses({
      path: "/orgs/{org}/search?q={query}",
      headers: [],
      body: "",
      sendsBody: false,
    });
    render(
      <ToolArgumentsField
        args={args}
        onChange={onChange}
        uses={uses}
        onAddToQuery={onAddToQuery}
      />,
    );
    expect(within(screen.getByTestId("argument-query")).getByText("?q=")).toBeInTheDocument();
    expect(within(screen.getByTestId("argument-status")).getByText("not used")).toBeInTheDocument();
    expect(screen.getByText(/status isn't used anywhere in the request/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add as query parameter" }));
    expect(onAddToQuery).toHaveBeenCalledWith("status");
    // `{org}` has no argument: Add argument org adds a required one.
    expect(screen.getByText(/no argument is named org/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add argument org" }));
    expect(onChange.mock.calls[0][0].at(-1)).toMatchObject({ name: "org", required: true });
  });
});

describe("ToolQueryField", () => {
  test("reads the rows from the path and writes an edit back to it", () => {
    const onChange = vi.fn();
    render(<ToolQueryField path="/search?q={query}&limit=10" onChange={onChange} />);
    expect(screen.getByLabelText("Value of q")).toHaveValue("{query}");
    fireEvent.change(screen.getByLabelText("Value of limit"), { target: { value: "{limit}" } });
    expect(onChange).toHaveBeenLastCalledWith("/search?q={query}&limit={limit}");
    fireEvent.click(screen.getByRole("button", { name: "Remove q" }));
    expect(onChange).toHaveBeenLastCalledWith("/search?limit=10");
  });
});
