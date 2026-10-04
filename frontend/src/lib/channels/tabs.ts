// frontend/src/lib/channels/tabs.ts
// A channel's detail tabs, in order — Overview (the default, at the bare
// `/channels/<uid>`) and Settings (`/channels/<uid>/settings`). Shared by the
// Channels page, which owns the address, and the pane that draws the tabs.
export const CHANNEL_TABS = ["overview", "settings"] as const;
export type ChannelTab = (typeof CHANNEL_TABS)[number];
export const DEFAULT_CHANNEL_TAB: ChannelTab = "overview";

/** The address of one channel on `tab` — the bare path for the default tab. */
export function channelPath(uid: string, tab: string = DEFAULT_CHANNEL_TAB): string {
  const base = `/channels/${encodeURIComponent(uid)}`;
  return tab === DEFAULT_CHANNEL_TAB ? base : `${base}/${tab}`;
}

/** Where "Conversations from this channel" leads: the Conversations page
 *  filtered to the conversations this channel started. */
export function channelConversationsHref(uid: string): string {
  return `/conversations?source=${encodeURIComponent(uid)}`;
}
