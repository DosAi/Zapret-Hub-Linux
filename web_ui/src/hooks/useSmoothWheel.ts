import { useEffect } from "react";

type ScrollState = {
  target: number;
  frame: number | null;
  lastTime: number;
};

const states = new WeakMap<HTMLElement, ScrollState>();

export function useSmoothWheel() {
  useEffect(() => {
    const onWheel = (event: WheelEvent) => {
      const target = event.target as HTMLElement | null;
      const scroller = target?.closest<HTMLElement>(".scroll-area");
      if (!scroller || target?.closest("textarea, input, select, .native-scroll")) return;

      const max = scroller.scrollHeight - scroller.clientHeight;
      if (max <= 0) return;

      const multiplier = event.deltaMode === WheelEvent.DOM_DELTA_LINE ? 20 : event.deltaMode === WheelEvent.DOM_DELTA_PAGE ? scroller.clientHeight : 1;
      const delta = event.deltaY * multiplier;
      if ((delta < 0 && scroller.scrollTop <= 0) || (delta > 0 && scroller.scrollTop >= max)) return;

      event.preventDefault();
      const state = states.get(scroller) ?? { target: scroller.scrollTop, frame: null, lastTime: 0 };
      if (state.frame === null) {
        state.target = scroller.scrollTop;
        state.lastTime = 0;
      }
      state.target = Math.max(0, Math.min(max, state.target + delta));
      states.set(scroller, state);

      if (state.frame !== null) return;
      const animate = (time: number) => {
        const elapsed = state.lastTime ? Math.min(34, time - state.lastTime) : 16.67;
        state.lastTime = time;
        const distance = state.target - scroller.scrollTop;
        if (Math.abs(distance) < 0.35) {
          scroller.scrollTop = state.target;
          state.frame = null;
          state.lastTime = 0;
          return;
        }
        const smoothing = 1 - Math.exp(-elapsed / 42);
        scroller.scrollTop += distance * smoothing;
        state.frame = requestAnimationFrame(animate);
      };
      state.frame = requestAnimationFrame(animate);
    };

    document.addEventListener("wheel", onWheel, { passive: false });
    return () => document.removeEventListener("wheel", onWheel);
  }, []);
}
