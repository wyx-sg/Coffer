// src/components/providers/Section.tsx — one titled section of a provider's Overview.
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface Props {
  title: string;
  /** Beside the title: a count, a summary, a link on the right (`ml-auto`). */
  aside?: ReactNode;
  gap?: "tight" | "normal";
  children: ReactNode;
}

export function Section({ title, aside, gap = "normal", children }: Props) {
  return (
    <section className={cn("flex flex-col", gap === "tight" ? "gap-1.5" : "gap-2.5")}>
      <div className="flex min-h-[26px] items-center gap-2">
        <h3 className="text-sm font-semibold text-text">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}
