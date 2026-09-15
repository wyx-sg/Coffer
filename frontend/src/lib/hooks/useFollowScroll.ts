// frontend/src/lib/hooks/useFollowScroll.ts — follow-the-stream scrolling for
// the message thread. The thread follows new content only while the user sits
// at the bottom; scrolling up to read history detaches, and `jumpToLatest`
// re-attaches. Opening another thread (`resetKey`) always starts at the bottom.
// The follow flag is a ref (read inside effects, so a token never re-renders
// the thread on its own account); `following` mirrors it for the UI pill.
import { useEffect, useRef, useState, type RefObject } from "react";

import { isNearBottom } from "@/lib/chat/scroll";

interface Options {
  /** The scrollable element. */
  scrollRef: RefObject<HTMLElement | null>;
  /** A sentinel at the end of the content to scroll into view. */
  bottomRef: RefObject<HTMLElement | null>;
  /** Changing this (another conversation) restarts at the bottom. */
  resetKey: string;
  /** Per-token updates jump instantly; smooth scrolling on every delta stutters. */
  isStreaming: boolean;
  /** Anything whose change means new content is on screen. */
  contentVersion: unknown;
}

export function useFollowScroll({
  scrollRef,
  bottomRef,
  resetKey,
  isStreaming,
  contentVersion,
}: Options) {
  const followRef = useRef(true);
  const [following, setFollowing] = useState(true);

  useEffect(() => {
    followRef.current = true;
    setFollowing(true);
    bottomRef.current?.scrollIntoView({ behavior: "auto" });
  }, [resetKey, bottomRef]);

  useEffect(() => {
    if (followRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: isStreaming ? "auto" : "smooth" });
    }
  }, [contentVersion, isStreaming, bottomRef]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const near = isNearBottom(el);
    if (near !== followRef.current) {
      followRef.current = near;
      setFollowing(near);
    }
  };

  const jumpToLatest = () => {
    followRef.current = true;
    setFollowing(true);
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  return { following, onScroll, jumpToLatest };
}
