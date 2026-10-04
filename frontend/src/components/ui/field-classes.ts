// src/components/ui/field-classes.ts
// The field look shared by input, textarea, select trigger and combobox trigger.
/** The field surface every text-like control shares: raised fill, 1px line,
 *  radius 7, 13/400. Focus is the accent border plus a soft 3px halo (no ring
 *  offset); `aria-invalid` swaps both for the danger pair; disabled sinks the
 *  fill and fades to .6. Read-only is added per control (a `<button>` trigger
 *  would match `:read-only` too). */
export const fieldClass = [
  "w-full rounded-md border border-border bg-surface-raised text-sm font-normal text-text",
  "placeholder:text-text-subtle",
  "transition-[border-color,box-shadow] duration-fast ease-standard",
  "focus-visible:border-accent focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-accent-soft",
  "aria-[invalid=true]:border-danger aria-[invalid=true]:ring-[3px] aria-[invalid=true]:ring-danger-soft",
  "disabled:cursor-not-allowed disabled:border-border-subtle disabled:bg-surface-sunken disabled:opacity-field-disabled",
].join(" ");

/** The read-only look for editable controls: same as disabled, but the value
 *  stays selectable. */
export const fieldReadOnlyClass =
  "read-only:border-border-subtle read-only:bg-surface-sunken read-only:opacity-field-disabled";
