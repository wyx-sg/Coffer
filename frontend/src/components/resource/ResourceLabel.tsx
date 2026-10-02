// src/components/resource/ResourceLabel.tsx
// A resource's on-screen name: its title with the name beside it as secondary
// text when a title is set, the name alone when not — for the kinds that carry
// a title (provider, channel, knowledge, memory). The name stays visible because
// it is what an agent sees.
import { TruncatedText } from "@/components/ui/truncated-text";
import { cn } from "@/lib/utils";
import { titleOf, type Titled } from "@/lib/resourceTitle";

interface Props {
  resource: Titled;
  /** A detail-page heading rather than a table cell: the title inherits the
   *  heading's size and the name reads a step larger than in a row. */
  heading?: boolean;
  className?: string;
  /** One line in a table cell: title and name end in an ellipsis. */
  truncate?: boolean;
}

export function ResourceLabel({ resource, heading = false, className, truncate = false }: Props) {
  const title = titleOf(resource);
  if (truncate) {
    return (
      <span className={cn("flex min-w-0 items-baseline gap-x-2", className)}>
        <TruncatedText text={title ?? resource.name} className="font-medium" />
        {title ? (
          <TruncatedText
            text={resource.name}
            mono
            className="max-w-[50%] shrink-0 text-xs text-muted-foreground"
          />
        ) : null}
      </span>
    );
  }
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
