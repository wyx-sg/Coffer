// frontend/src/lib/components/ResourceListView.tsx
import { useTranslation } from "react-i18next";
import { Card, CardContent } from "@/components/ui/card";
import { type ResourceOut, getKindUI } from "./kindRegistry";

interface Props {
  resources: ResourceOut[];
  emptyMessage?: string;
}

export function ResourceListView({ resources, emptyMessage }: Props) {
  const { t } = useTranslation();
  if (resources.length === 0) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          {emptyMessage ?? t("resources.noMatches")}
        </CardContent>
      </Card>
    );
  }
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {resources.map((resource) => {
        const kindUI = getKindUI(resource.kind);
        if (kindUI === undefined) {
          return <UnknownKindCard key={resource.ref} resource={resource} />;
        }
        const KindCard = kindUI.Card;
        return <KindCard key={resource.ref} resource={resource} />;
      })}
    </div>
  );
}

function UnknownKindCard({ resource }: { resource: ResourceOut }) {
  return (
    <Card>
      <CardContent className="py-4">
        <div className="font-medium">{resource.name}</div>
        <div className="text-xs text-muted-foreground">unregistered kind: {resource.kind}</div>
      </CardContent>
    </Card>
  );
}
