import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Label } from "./label";

describe("Label", () => {
  it("marks a required field after its text, leaving the accessible name as the word", () => {
    render(<Label required>Name</Label>);
    const label = screen.getByText("Name");
    expect(label.className).toContain("after:content-['*']");
    expect(label.className).toContain("after:text-destructive");
    expect(label.textContent).toBe("Name");
    expect(label.hasAttribute("required")).toBe(false);
  });

  it("carries no mark on an optional field", () => {
    render(<Label>Description</Label>);
    expect(screen.getByText("Description").className).not.toContain("after:content");
  });
});
