// frontend/src/kinds/memory/index.tsx
import { Brain } from "lucide-react";
import type { KindUIModule } from "@/lib/components/kindRegistry";
import { MemoryDetailPage } from "./MemoryDetailPage";

export const MEMORY_KIND_UI: KindUIModule = {
  name: "memory",
  displayName: "Memory",
  icon: Brain,
  // A partition is named by its project's slug, so its row says what a
  // partition says: the name aggregation gave it.
  Card: ({ resource }) => <span className="font-medium">{resource.name}</span>,
  // No `addPath`: partitions are created by aggregation only (spec memory
  // FR-013), never by the user, so there is no "add" flow to route to.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  DetailPage: ({ name: _name }) => <MemoryDetailPage />,
};
