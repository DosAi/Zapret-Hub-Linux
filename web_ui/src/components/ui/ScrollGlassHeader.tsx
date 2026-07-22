import { type ReactNode, type RefObject, useEffect, useRef } from "react";

function sanitizeMirrorClone(root: HTMLElement) {
  root.querySelectorAll<HTMLElement>("*").forEach((node) => {
    node.style.opacity = "";
    node.style.transform = "";
    node.style.filter = "";
    node.style.visibility = "";
    node.style.pointerEvents = "none";
  });
  root.style.opacity = "";
  root.style.transform = "";
  root.style.filter = "";
}

export function ScrollGlassHeader({
  scrollerRef,
  children,
  className = "",
  foregroundClassName = "",
  contentKey,
}: {
  scrollerRef: RefObject<HTMLDivElement | null>;
  children: ReactNode;
  className?: string;
  foregroundClassName?: string;
  /** Remount/rebuild mirror when page content identity changes (e.g. settings tab). */
  contentKey?: string | number;
}) {
  const mirrorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const scroller = scrollerRef.current;
    const mirror = mirrorRef.current;
    const source = scroller?.querySelector<HTMLElement>(".scroll-content");
    if (!scroller || !mirror || !source) return;

    let clone: HTMLElement | null = null;
    let syncFrame = 0;
    let rebuildTimer = 0;
    let settleTimer = 0;

    const sync = () => {
      syncFrame = 0;
      if (clone) clone.style.transform = `translate3d(0, ${-scroller.scrollTop}px, 0)`;
    };
    const scheduleSync = () => {
      if (!syncFrame) syncFrame = requestAnimationFrame(sync);
    };
    const rebuild = () => {
      rebuildTimer = 0;
      clone = source.cloneNode(true) as HTMLElement;
      clone.classList.add("scroll-header-mirror-content");
      clone.setAttribute("aria-hidden", "true");
      clone.querySelectorAll("[id]").forEach((node) => node.removeAttribute("id"));
      sanitizeMirrorClone(clone);
      mirror.replaceChildren(clone);
      sync();
    };
    const scheduleRebuild = () => {
      if (rebuildTimer) window.clearTimeout(rebuildTimer);
      rebuildTimer = window.setTimeout(rebuild, 48);
      if (settleTimer) window.clearTimeout(settleTimer);
      // Catch content after tab / page enter animations finish.
      settleTimer = window.setTimeout(rebuild, 220);
    };

    rebuild();
    settleTimer = window.setTimeout(rebuild, 220);
    scroller.addEventListener("scroll", scheduleSync, { passive: true });
    const observer = new MutationObserver(scheduleRebuild);
    observer.observe(source, { childList: true, subtree: true });
    return () => {
      scroller.removeEventListener("scroll", scheduleSync);
      observer.disconnect();
      if (syncFrame) cancelAnimationFrame(syncFrame);
      if (rebuildTimer) window.clearTimeout(rebuildTimer);
      if (settleTimer) window.clearTimeout(settleTimer);
    };
  }, [scrollerRef, contentKey]);

  return (
    <div className={`scroll-header ${className}`}>
      <div ref={mirrorRef} className="scroll-header-mirror" aria-hidden="true" />
      <div className="scroll-header-glass-tint" aria-hidden="true" />
      <div className={`scroll-header-foreground ${foregroundClassName}`}>{children}</div>
    </div>
  );
}
