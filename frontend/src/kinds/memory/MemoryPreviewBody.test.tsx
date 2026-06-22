// frontend/src/kinds/memory/MemoryPreviewBody.test.tsx
//
// The shared memory preview renders a leading frontmatter block as a clean
// header (title + description + meta line) and the body below — the raw `---`
// fences must NOT survive into the Markdown (where they would become an <hr>).
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryPreviewBody } from "./MemoryPreviewBody";

describe("MemoryPreviewBody", () => {
  test("renders frontmatter title/description as a header and the body below", () => {
    const { container } = render(
      <MemoryPreviewBody
        text={"---\ntitle: Deploy\ndescription: how it ships\nbranch: main\n---\nbody line"}
      />,
    );
    expect(screen.getByText("Deploy")).toBeInTheDocument();
    expect(screen.getByText("how it ships")).toBeInTheDocument();
    expect(screen.getByText("main")).toBeInTheDocument();
    expect(screen.getByText("body line")).toBeInTheDocument();
    // The frontmatter fences must not render as a horizontal rule.
    expect(container.querySelector("hr")).toBeNull();
  });

  test("renders plain text as-is when there is no frontmatter", () => {
    render(<MemoryPreviewBody text={"just a body"} />);
    expect(screen.getByText("just a body")).toBeInTheDocument();
  });

  test("suppresses the header description when hideDescription is set", () => {
    render(
      <MemoryPreviewBody text={"---\ntitle: T\ndescription: D\n---\nb"} hideDescription />,
    );
    expect(screen.getByText("T")).toBeInTheDocument();
    expect(screen.queryByText("D")).toBeNull();
  });
});
