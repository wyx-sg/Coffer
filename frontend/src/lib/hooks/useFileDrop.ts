// src/lib/hooks/useFileDrop.ts
// Drag-and-drop of files onto one element (the chat composer). A file drag over
// it is always claimed with preventDefault — even while disabled — because an
// unclaimed drop makes the browser navigate to the file and lose the page.
// Disabled, a drop attaches nothing and shows no highlight.
//
// dragenter/dragleave fire for every child element the pointer crosses, so the
// highlight tracks their depth and only drops when the drag really leaves.
import { useRef, useState, type DragEvent } from "react";

const isFileDrag = (e: DragEvent) => Array.from(e.dataTransfer.types).includes("Files");

export function useFileDrop(disabled: boolean, onFiles: (files: File[]) => void) {
  const [dragging, setDragging] = useState(false);
  const depth = useRef(0);

  const handlers = {
    onDragEnter: (e: DragEvent<HTMLElement>) => {
      if (!isFileDrag(e)) return;
      e.preventDefault();
      depth.current += 1;
      if (!disabled) setDragging(true);
    },
    onDragOver: (e: DragEvent<HTMLElement>) => {
      if (!isFileDrag(e)) return;
      e.preventDefault();
      if (!disabled) setDragging(true);
    },
    onDragLeave: (e: DragEvent<HTMLElement>) => {
      if (!isFileDrag(e)) return;
      depth.current = Math.max(0, depth.current - 1);
      if (depth.current === 0) setDragging(false);
    },
    onDrop: (e: DragEvent<HTMLElement>) => {
      if (!isFileDrag(e)) return;
      e.preventDefault();
      depth.current = 0;
      setDragging(false);
      if (!disabled) onFiles(Array.from(e.dataTransfer.files));
    },
  };

  return { dragging, handlers };
}
