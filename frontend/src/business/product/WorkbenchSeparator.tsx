import { useCallback, useEffect, useRef } from "react";
import { dragPanelWidth, keyPanelWidth } from "./workbench-resize";

interface Drag { x: number; width: number; pointerId: number; handle: HTMLDivElement; scope: HTMLElement | null }

export default function WorkbenchSeparator({ label, width, min, max, direction = 1, onResize, className = "" }: {
  label: string; width: number; min: number; max: number; direction?: 1 | -1;
  onResize: (width: number) => void; className?: string;
}) {
  const drag = useRef<Drag | null>(null);
  const finish = useCallback(() => {
    const current = drag.current;
    if (!current) return;
    drag.current = null;
    if (current.scope) delete current.scope.dataset.resizing;
    if (current.handle.hasPointerCapture(current.pointerId)) current.handle.releasePointerCapture(current.pointerId);
  }, []);
  useEffect(() => finish, [finish]);
  return <div role="separator" aria-orientation="vertical" aria-label={label} aria-valuemin={min} aria-valuemax={max} aria-valuenow={width} aria-valuetext={`${width} 像素`} tabIndex={0} className={`wb-width-separator ${className}`} title={`${label}：拖动或使用左右方向键`} onPointerDown={event => {
    if (event.button !== 0 || !event.isPrimary || drag.current) return;
    event.preventDefault();
    const handle = event.currentTarget;
    handle.focus({ preventScroll: true });
    handle.setPointerCapture(event.pointerId);
    const scope = handle.closest<HTMLElement>(".wb-shell");
    if (scope) scope.dataset.resizing = "true";
    drag.current = { x: event.clientX, width, pointerId: event.pointerId, handle, scope };
  }} onPointerMove={event => {
    const current = drag.current;
    if (current?.pointerId === event.pointerId) onResize(dragPanelWidth(current.width, event.clientX - current.x, direction, min, max));
  }} onPointerUp={finish} onPointerCancel={finish} onLostPointerCapture={finish} onKeyDown={event => {
    const next = keyPanelWidth(width, event.key, direction, min, max);
    if (next !== null) { event.preventDefault(); onResize(next); }
  }}/>;
}
