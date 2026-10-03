// src/components/ui/skeleton.test.tsx
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";

import { acceptance } from "@/test/acceptance";
import { PageFallback } from "@/components/PageFallback";

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

  acceptance("web-ui", "a loading placeholder waits 300 ms before it shows", () => {
    // `animate-shimmer` and `animate-appear` both begin with the 300 ms
    // delayed appearance (tailwind.config.js), so neither paints before it.
    const { container } = render(
      <>
        <Skeleton />
        <PageFallback />
      </>,
    );
    expect((container.firstElementChild as HTMLElement).className).toContain("animate-shimmer");
    expect(screen.getByRole("status").className).toContain("animate-appear");
  });
});
