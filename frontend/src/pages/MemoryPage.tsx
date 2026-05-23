// frontend/src/pages/MemoryPage.tsx
import { BrainCircuit } from "lucide-react";
import { KindResourcePage } from "./KindResourcePage";

/** Memory-stores landing page (spec 007-memory). */
export function MemoryPage() {
  return <KindResourcePage kind="memory" icon={BrainCircuit} i18nKey="memory" />;
}
