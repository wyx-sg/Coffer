// src/components/sessions/MenuSpacer.tsx — the ⋯ menu's place on a session row with no menu.
//
// A row whose agent can neither rename nor delete (Cursor, DeepSeek Harness)
// keeps the menu button's width, so its buttons line up with the rows around it.
export function MenuSpacer() {
  return (
    <span aria-hidden data-testid="session-menu-spacer" className="size-control-sm shrink-0" />
  );
}
