// frontend/src/components/mcp/declaresParameters.ts
//
// A tool schema that declares no parameters (`{}`, or an object schema whose
// `properties` is missing or empty) carries nothing worth showing; the
// capability list treats it as absent so the row detail reads "no parameters"
// instead of a bare `{}`.
export function declaresParameters(schema: Record<string, unknown> | undefined): boolean {
  if (!schema) return false;
  const props = schema.properties;
  if (props === undefined) return Object.keys(schema).some((k) => k !== "type");
  return typeof props === "object" && props !== null && Object.keys(props).length > 0;
}
