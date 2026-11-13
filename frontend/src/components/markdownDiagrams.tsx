// frontend/src/components/markdownDiagrams.tsx
// Routes a ```mermaid fenced block in the shared Markdown renderer to
// MermaidDiagram; every other <pre> renders as the renderer would have it.
import type { ComponentType } from "react";
import type { Components, ExtraProps } from "react-markdown";

import { MermaidDiagram } from "@/components/MermaidDiagram";

type Element = NonNullable<ExtraProps["node"]>;
type ElementContent = Element["children"][number];
type PreProps = NonNullable<Parameters<Extract<Components["pre"], (p: never) => unknown>>[0]>;

function textOf(node: ElementContent): string {
  if (node.type === "text") return node.value;
  if (node.type === "element") return node.children.map(textOf).join("");
  return "";
}

/** The source of a ```mermaid fenced block, or null for any other <pre>. */
function mermaidSource(pre: Element | undefined): string | null {
  const code = pre?.children.find(
    (child): child is Element => child.type === "element" && child.tagName === "code",
  );
  const classes = code?.properties.className;
  if (!code || !Array.isArray(classes) || !classes.includes("language-mermaid")) return null;
  return textOf(code).replace(/\n$/, "");
}

/** `pre` that draws a mermaid block and leaves every other block to `Pre`. */
export function withDiagrams(Pre: Components["pre"]): Components["pre"] {
  const Inner: ComponentType<PreProps> | "pre" =
    typeof Pre === "function" ? (Pre as ComponentType<PreProps>) : "pre";
  return function DiagramOrPre(props: PreProps) {
    const source = mermaidSource(props.node);
    if (source !== null) return <MermaidDiagram source={source} />;
    if (Inner !== "pre") return <Inner {...props} />;
    // A plain <pre> takes no hast `node`, as react-markdown itself would give it.
    const rest = { ...props };
    delete rest.node;
    return <pre {...rest} />;
  };
}
