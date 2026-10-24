"use client";

import { useCallback, useEffect, useRef } from "react";
import { nextPollDelay } from "./polling";

/**
 * Calls `load` now and then every `interval` ms, one request at a time.
 * Pauses while the tab is hidden and loads again when it comes back; after a failure the
 * delay doubles up to a minute. `refresh()` loads right away (after a user action).
 */
export function usePolling(load: (signal: AbortSignal) => Promise<void>, interval: number, key: string, enabled = true) {
  const loadRef = useRef(load);
  useEffect(() => { loadRef.current = load; });
  const triggerRef = useRef<() => void>(() => {});

  useEffect(() => {
    if (!enabled) return;
    let stopped = false;
    let running = false;
    let again = false;
    let failures = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();

    async function tick() {
      if (stopped) return;
      clearTimeout(timer);
      if (document.hidden) return;
      if (running) { again = true; return; }
      running = true;
      try {
        await loadRef.current(controller.signal);
        failures = 0;
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        failures += 1;
      } finally {
        running = false;
      }
      if (stopped) return;
      if (again) { again = false; void tick(); return; }
      timer = setTimeout(tick, nextPollDelay(interval, failures));
    }

    function onVisibility() { if (!document.hidden) void tick(); }
    triggerRef.current = () => { void tick(); };
    document.addEventListener("visibilitychange", onVisibility);
    void tick();
    return () => {
      stopped = true;
      clearTimeout(timer);
      controller.abort();
      document.removeEventListener("visibilitychange", onVisibility);
      triggerRef.current = () => {};
    };
  }, [interval, key, enabled]);

  return useCallback(() => triggerRef.current(), []);
}
