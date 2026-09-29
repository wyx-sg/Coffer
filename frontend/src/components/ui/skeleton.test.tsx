// src/components/ui/skeleton.test.tsx
import { describe, expect, test } from "vitest";
import { render } from "@testing-library/react";

import { Skeleton } from "./skeleton";

describe("Skeleton", () => {
  test("renders a shimmering sunken block hidden from assistive tech", () => {
    const { container } = render(<Skeleton data-testid="sk" />);
    const el = container.firstElementChild as HTMLElement;
    expect(el).toHaveAttribute("aria-hidden", "true");
    expect(el.className).toContain("animate-shimmer");
    expect(el.className).toContain("bg-surface-sunken");
  });

  test("merges the caller's sizing classes", () => {
    const { container } = render(<Skeleton className="h-4 w-24" />);
    const el = container.firstElementChild as HTMLElement;
    expect(el.className).toContain("h-4");
    expect(el.className).toContain("w-24");
  });
});
