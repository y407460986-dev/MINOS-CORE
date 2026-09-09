import { useEffect, type RefObject } from "react";

type DragScrollOptions = {
  /** Require holding Shift key to activate drag scroll. Default true. */
  requireShiftKey?: boolean;
  /** Scroll speed multiplier. Default 2. */
  speed?: number;
};

/**
 * Enables mouse drag-to-scroll on a container. Hold Shift + drag to scroll
 * horizontally. Inspired by Figma / Notion canvas interaction.
 */
export function useDragScroll(
  ref: RefObject<HTMLElement | null>,
  options: DragScrollOptions = {},
) {
  const { requireShiftKey = true, speed = 2 } = options;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    let dragging = false;
    let startX = 0;
    let startY = 0;
    let scrollLeft = 0;
    let scrollTop = 0;

    const onDown = (e: MouseEvent) => {
      if (requireShiftKey && !e.shiftKey) return;
      dragging = true;
      startX = e.clientX;
      startY = e.clientY;
      scrollLeft = el.scrollLeft;
      scrollTop = el.scrollTop;
      el.style.cursor = "grabbing";
      el.style.userSelect = "none";
    };

    const onMove = (e: MouseEvent) => {
      if (!dragging) return;
      e.preventDefault();
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      el.scrollLeft = scrollLeft - dx * speed;
      el.scrollTop = scrollTop - dy * speed;
    };

    const onUp = () => {
      if (!dragging) return;
      dragging = false;
      el.style.cursor = "";
      el.style.userSelect = "";
    };

    el.addEventListener("mousedown", onDown);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);

    el.style.cursor = requireShiftKey ? "default" : "grab";

    return () => {
      el.removeEventListener("mousedown", onDown);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      el.style.cursor = "";
      el.style.userSelect = "";
    };
  }, [ref, requireShiftKey, speed]);
}
