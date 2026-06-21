// frontend/src/components/FileActions.tsx
// Coffer's file viewers are read-only (specs 002/004/005/006/007): editing
// happens in the user's own editor, not in-app. This shared action bar takes a
// managed file to those external tools — open it in the preferred editor (see
// the "preferred editor" preference in General settings) and reveal it in the OS
// file manager. The web and desktop surfaces show the same buttons.
//
// The actions themselves live in lib/fileActionItems.ts (`useFileActionItems`)
// so a crowded table row can fold the same open/reveal into the RowActions "⋯"
// overflow menu instead of spelling out every button inline.
import { useFileActionItems } from "@/lib/fileActionItems";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function FileActions({
  filePath,
  className,
}: {
  /** Absolute on-disk path of the file being viewed. */
  filePath: string;
  className?: string;
}) {
  const items = useFileActionItems(filePath);
  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      {items.map((it) => {
        const Icon = it.icon;
        return (
          <Button key={it.key} type="button" size="sm" variant="outline" onClick={it.onClick}>
            <Icon className="mr-1.5 size-3.5" />
            {it.label}
          </Button>
        );
      })}
    </div>
  );
}
