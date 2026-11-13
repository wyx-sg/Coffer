// frontend/src/components/Markdown.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";

const mermaid = vi.hoisted(() => ({
  initialize: vi.fn(),
  parse: vi.fn(async () => ({})),
  render: vi.fn(async () => ({ svg: '<svg data-testid="drawn"><text>A to B</text></svg>' })),
}));
vi.mock("mermaid", () => ({ default: mermaid }));

import { acceptance } from "@/test/acceptance";

import { Markdown } from "./Markdown";

describe("Markdown", () => {
  test("demotes headings one level so a document never adds a second h1", () => {
    render(<Markdown>{"# Title\n\n## Section\n\n###### Deep"}</Markdown>);
    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("Title");
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent("Section");
    expect(screen.getByRole("heading", { level: 6 })).toHaveTextContent("Deep");
  });

  test("inline code stays on the type scale", () => {
    render(<Markdown>{"use `coffer daemon start`"}</Markdown>);
    const code = screen.getByText("coffer daemon start");
    expect(code.tagName).toBe("CODE");
    expect(code.className).toContain("text-xs");
  });

  describe("mermaid blocks", () => {
    const diagram = "```mermaid\nflowchart LR\n  A --> B\n```";

    beforeEach(() => {
      mermaid.initialize.mockClear();
      mermaid.parse.mockReset().mockResolvedValue({});
      mermaid.render.mockClear();
    });

    acceptance("web-ui", "a mermaid block shows as its diagram", async () => {
      render(<Markdown>{diagram}</Markdown>);
      expect(await screen.findByTestId("mermaid-diagram")).toContainElement(
        screen.getByTestId("drawn"),
      );
      expect(mermaid.render).toHaveBeenCalledWith(expect.any(String), "flowchart LR\n  A --> B");
      expect(mermaid.initialize).toHaveBeenCalledWith(
        expect.objectContaining({ securityLevel: "strict", startOnLoad: false }),
      );
    });

    acceptance("web-ui", "a diagram that cannot be drawn shows its source", async () => {
      mermaid.parse.mockRejectedValue(new Error("Parse error on line 1"));
      render(<Markdown>{"```mermaid\nnot a diagram\n```"}</Markdown>);
      expect(await screen.findByTestId("mermaid-failed")).toBeInTheDocument();
      expect(screen.getByTestId("mermaid-source")).toHaveTextContent("not a diagram");
      expect(mermaid.render).not.toHaveBeenCalled();
      expect(screen.queryByTestId("mermaid-diagram")).not.toBeInTheDocument();
    });

    acceptance("web-ui", "conversation text draws diagrams and keeps Copy on code", async () => {
      render(
        <Markdown density="chat" copyableCode highlight>
          {`${diagram}\n\n\`\`\`sh\nls\n\`\`\``}
        </Markdown>,
      );
      expect(await screen.findByTestId("mermaid-diagram")).toBeInTheDocument();
      expect(screen.getAllByRole("button", { name: /copy/i })).toHaveLength(1);
    });
  });
});
