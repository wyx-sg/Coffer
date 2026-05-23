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
  // CODE26-036: router registers this page at ``/memory/new`` (see
  // ``router.tsx``). The previous ``/resources/memory/new`` value rendered
  // a 404 when the user clicked "Add memory store" from the resources
  // dashboard. The corresponding KB entry uses ``/knowledge-bases/new``
  // and was added/audited separately.
  addPath: "/memory/new",
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  DetailPage: ({ name: _name }) => <MemoryStoreDetailPage />,
};
