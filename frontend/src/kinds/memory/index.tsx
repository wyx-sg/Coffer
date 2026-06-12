// frontend/src/kinds/memory/index.tsx
import { Brain } from "lucide-react";
import type { KindUIModule } from "@/lib/components/kindRegistry";
import { MemoryStoreCard } from "./MemoryStoreCard";
import { MemoryStoreDetailPage } from "./MemoryStoreDetailPage";

export const MEMORY_KIND_UI: KindUIModule = {
  name: "memory",
  displayName: "Memory Store",
  icon: Brain,
  Card: MemoryStoreCard,
  // No ``addPath``: memory stores are auto-provisioned (a global store plus one
  // per project), so there is no "Add store" surface to link to.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  DetailPage: ({ name: _name }) => <MemoryStoreDetailPage />,
};
