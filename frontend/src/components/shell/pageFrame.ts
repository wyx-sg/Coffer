// src/components/shell/pageFrame.ts — the one frame for a full-bleed workspace page.
//
// Layout pads every page 32px at each side, 16 above and 40 below. A workspace
// page whose panes scroll on their own (Skills, Channels, Conversations…) takes
// that padding back with PAGE_BLEED, then puts its header row in PAGE_BLEED_HEAD
// so its title lands exactly where an ordinary page's does: 16px under the
// title strip, 32px in from the sidebar.

/** Undo Layout's padding and fill the scroll area (`h-screen` shrinks by the title strip in index.css). */
export const PAGE_BLEED = "-mx-8 -mb-10 -mt-4 flex h-screen overflow-hidden";

/** The header row's padding inside a PAGE_BLEED page; add only the space below it. */
export const PAGE_BLEED_HEAD = "px-8 pt-4";
