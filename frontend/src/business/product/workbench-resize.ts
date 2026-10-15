import { useEffect, useState } from "react";
import type { RefObject } from "react";

export function clampPanelWidth(width: number, min: number, max: number) {
  return Math.round(Math.min(Math.max(width, min), Math.max(min, max)));
}

export function dragPanelWidth(width: number, movement: number, direction: 1 | -1, min: number, max: number) {
  return clampPanelWidth(width + movement * direction, min, max);
}

export function keyPanelWidth(width: number, key: string, direction: 1 | -1, min: number, max: number) {
  if (key === "Home") return min;
  if (key === "End") return max;
  if (key !== "ArrowLeft" && key !== "ArrowRight") return null;
  return dragPanelWidth(width, key === "ArrowRight" ? 10 : -10, direction, min, max);
}

export function useElementWidth(ref: RefObject<HTMLElement | null>) {
  const [width, setWidth] = useState(0);
  useEffect(() => {
    if (!ref.current) return;
    const observer = new ResizeObserver(entries => setWidth(entries[0].contentRect.width));
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [ref]);
  return width;
}
