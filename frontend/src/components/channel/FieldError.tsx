// frontend/src/components/channel/FieldError.tsx
// Beneath a channel form field, `FieldError` renders the translated message a
// zod issue mapped to, or nothing. The field's required mark is `<Label
// required>`; `aria-required` on the input is what assistive tech reads.
export function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <p id={id} className="text-xs text-destructive" role="alert">
      {message}
    </p>
  );
}
