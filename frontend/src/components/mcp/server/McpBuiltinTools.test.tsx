// src/components/mcp/server/McpBuiltinTools.test.tsx — the built-in coffer server's tool rows open to their details on the Tools tab (spec web-ui "Show the built-in coffer server read-only").
import { describe, expect, test } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { acceptance } from "@/test/acceptance";
import { McpBuiltinTools } from "./McpBuiltinTools";

const tools = [
  {
    name: "search_tools",
    qualified_name: "coffer__search_tools",
    description: "Find a tool by what it does.",
    input_schema: { type: "object", properties: { query: { type: "string" } } },
  },
];
const summary = { calls: 0, errors: 0, by_agent: [], by_tool: [] };

describe("McpBuiltinTools", () => {
  acceptance("web-ui", "a built-in tool row opens to its details", () => {
    render(<McpBuiltinTools tools={tools} summary={summary as never} />);
    expect(screen.queryByTestId("mcp-builtin-tool-detail")).toBeNull();
    fireEvent.click(screen.getByText("search_tools"));
    const detail = screen.getByTestId("mcp-builtin-tool-detail");
    expect(detail).toHaveTextContent("query · string");
    expect(detail).toHaveTextContent("coffer__search_tools");
    fireEvent.click(screen.getByText("search_tools"));
    expect(screen.queryByTestId("mcp-builtin-tool-detail")).toBeNull();
  });

  test("the Overview's most-called list does not open", () => {
    render(<McpBuiltinTools tools={tools} summary={summary as never} top />);
    fireEvent.click(screen.getByText("search_tools"));
    expect(screen.queryByTestId("mcp-builtin-tool-detail")).toBeNull();
  });
});
