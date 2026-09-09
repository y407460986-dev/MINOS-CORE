import { useEffect, useRef, type RefObject } from "react";

type Props = {
  targetRef: RefObject<HTMLElement | null>;
  className?: string;
};

/**
 * Renders a sticky horizontal scrollbar that syncs with a target scroll container.
 * The scrollbar stays visible at the bottom of the viewport even when the target
 * container's native scrollbar is scrolled out of view.
 */
export function StickyHorizontalScrollbar({ targetRef, className = "" }: Props) {
  const scrollbarRef = useRef<HTMLDivElement>(null);
  const spacerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const target = targetRef.current;
    const scrollbar = scrollbarRef.current;
    const spacer = spacerRef.current;
    if (!target || !scrollbar || !spacer) return;

    let syncing = false;

    const updateWidth = () => {
      const w = target.scrollWidth;
      spacer.style.width = `${w}px`;
    };

    const syncFromTarget = () => {
      if (syncing) return;
      syncing = true;
      scrollbar.scrollLeft = target.scrollLeft;
      syncing = false;
    };

    const syncFromScrollbar = () => {
      if (syncing) return;
      syncing = true;
      target.scrollLeft = scrollbar.scrollLeft;
      syncing = false;
    };

    const observer = new ResizeObserver(updateWidth);
    observer.observe(target);

    target.addEventListener("scroll", syncFromTarget, { passive: true });
    scrollbar.addEventListener("scroll", syncFromScrollbar, { passive: true });

    updateWidth();

    return () => {
      observer.disconnect();
      target.removeEventListener("scroll", syncFromTarget);
      scrollbar.removeEventListener("scroll", syncFromScrollbar);
    };
  }, [targetRef]);

  return (
    <div
      ref={scrollbarRef}
      className={`sticky bottom-0 z-10 overflow-x-auto overflow-y-hidden border-t border-border bg-white ${className}`}
      style={{ height: 14 }}
    >
      <div ref={spacerRef} style={{ height: 1, minWidth: "100%" }} />
    </div>
  );
}
