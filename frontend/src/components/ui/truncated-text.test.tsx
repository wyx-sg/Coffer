// src/components/ui/truncated-text.test.tsx — the one-line, ellipsis-with-tooltip cell helpers.
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DataTable } from "@/components/DataTable";
import { splitPath, TruncatedPath, TruncatedText } from "@/components/ui/truncated-text";

describe("TruncatedText", () => {
  it("renders one clipped line carrying the full text", () => {
    const long = "x".repeat(300);
    render(<TruncatedText text={long} mono />);
    const el = screen.getByText(long);
    expect(el.className).toContain("truncate");
    expect(el.className).toContain("font-mono");
    expect(el.className).toContain("min-w-0");
  });
});

describe("TruncatedPath", () => {
  it("keeps the last segment out of the clipped part", () => {
    expect(splitPath("~/.claude/skills/coffer-configuring-service")).toEqual({
      head: "~/.claude/skills/",
      tail: "coffer-configuring-service",
    });
    expect(splitPath("name-only")).toEqual({ head: "", tail: "name-only" });
    expect(splitPath("/a/b/")).toEqual({ head: "/a/", tail: "b" });
  });

  it("clips the head and protects the tail", () => {
    const { container } = render(
      <TruncatedPath text="~/.claude/skills/coffer-configuring-service" />,
    );
    const root = container.querySelector("[data-truncated-path]")!;
    const [head, tail] = Array.from(root.children);
    expect(head.className).toContain("truncate");
    expect(head.className).toContain("shrink");
    expect(tail.className).toContain("shrink-0");
    expect(tail.textContent).toBe("coffer-configuring-service");
  });
});

describe("DataTable fixed", () => {
  it("uses the fixed table layout only when asked", () => {
    const cols = [
      { key: "a", header: "A", cell: (r: { id: string }) => r.id, className: "w-[30%]" },
    ];
    const { rerender } = render(
      <DataTable rows={[{ id: "1" }]} columns={cols} rowKey={(r) => r.id} emptyMessage="none" />,
    );
    expect(screen.getByRole("table").className).not.toContain("table-fixed");
    rerender(
      <DataTable
        fixed
        rows={[{ id: "1" }]}
        columns={cols}
        rowKey={(r) => r.id}
        emptyMessage="none"
      />,
    );
    expect(screen.getByRole("table").className).toContain("table-fixed");
    expect(screen.getByRole("columnheader").className).toContain("w-[30%]");
  });
});
