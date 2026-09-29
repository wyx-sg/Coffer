// src/components/resource/ResourceLabel.tsx
// A resource's on-screen name: its title with the name beside it as secondary
// text when a title is set, the name alone when not (spec web-ui "Show and edit
// a title on MCP server and skill pages"). The name stays visible because it is
// what an agent sees.
import { cn } from "@/lib/utils";
import { titleOf, type Titled } from "@/lib/resourceTitle";

interface Props {
  resource: Titled;
  /** A detail-page heading rather than a table cell: the title inherits the
   *  heading's size and the name reads a step larger than in a row. */
  heading?: boolean;
  className?: string;
}

export function ResourceLabel({ resource, heading = false, className }: Props) {
  const title = titleOf(resource);
  if (!title) {
    return <span className={cn(!heading && "font-medium", className)}>{resource.name}</span>;
  }
  return (
    <span className={cn("inline-flex flex-wrap items-baseline gap-x-2", className)}>
      <span className={cn(!heading && "font-medium")}>{title}</span>
      <span
        data-slot="resource-name"
        className={cn("font-mono text-muted-foreground", heading ? "text-sm" : "text-xs")}
      >
        {resource.name}
      </span>
    </span>
  );
}
