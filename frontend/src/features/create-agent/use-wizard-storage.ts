"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api/client";
import { blankSnapshot, GUEST_KEY, guestSnapshot, restoredSnapshot, snapshotBody, type SavedWizard, type Snapshot } from "./wizard-persistence";

type Status = "loading" | "saved" | "dirty" | "saving" | "error" | "conflict" | "expired";
export type WizardMode = "account" | "guest" | "unavailable";

export function useWizardStorage(mode: WizardMode) {
  const [snapshot, setSnapshot] = useState<Snapshot>(blankSnapshot);
  const [status, setStatus] = useState<Status>("loading");
  const [ready, setReady] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [guest, setGuest] = useState<Snapshot | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const latest = useRef(snapshot);
  const acknowledged = useRef("");
  const version = useRef(0);
  const inflight = useRef<Promise<boolean> | null>(null);
  const statusRef = useRef<Status>("loading");
  const readyRef = useRef(false);
  const mounted = useRef(true);
  const loadEpoch = useRef(0);
  const completing = useRef(false);
  const [finishing, setFinishing] = useState(false);
  const setState = useCallback((value: Status) => { statusRef.current = value; if (mounted.current) setStatus(value); }, []);

  const change = useCallback((update: (previous: Snapshot) => Snapshot) => {
    if (!readyRef.current || !mounted.current || completing.current) return;
    const next = update(latest.current);
    latest.current = next;
    setSnapshot(next);
    setCompleted(false);
    if (!["conflict", "expired"].includes(statusRef.current)) setState("dirty");
  }, [setState]);

  const load = useCallback(async () => {
    const epoch = ++loadEpoch.current;
    if (inflight.current) await inflight.current;
    setState("loading"); setFailure(null); readyRef.current = false; setReady(false);
    try {
      if (mode === "unavailable") throw new Error("unavailable");
      let savedGuest: Snapshot | null = null;
      try { savedGuest = guestSnapshot(sessionStorage.getItem(GUEST_KEY)); } catch { /* Storage can be blocked. */ }
      const row = mode === "account" ? await api<SavedWizard>("onboarding") : null;
      if (!mounted.current || epoch !== loadEpoch.current) return;
      const value = row ? restoredSnapshot(row) : savedGuest ?? blankSnapshot();
      latest.current = value; acknowledged.current = JSON.stringify(value); version.current = row?.version ?? 0;
      setSnapshot(value); setCompleted(Boolean(row?.completed_at)); setGuest(row && !row.data ? savedGuest : null);
      readyRef.current = true; setReady(true); setState("saved");
    } catch (error) {
      if (!mounted.current || epoch !== loadEpoch.current) return;
      setFailure(error instanceof ApiError ? error.code : "unavailable");
      setState(error instanceof ApiError && error.unauthenticated ? "expired" : "error");
    }
  }, [mode, setState]);

  useEffect(() => {
    mounted.current = true;
    void load();
    return () => { mounted.current = false; loadEpoch.current += 1; };
  }, [load]);

  const flush = useCallback(async (): Promise<boolean> => {
    if (!readyRef.current || ["conflict", "expired"].includes(statusRef.current)) return false;
    if (inflight.current) return inflight.current;
    const operation = async () => {
      try {
        while (JSON.stringify(latest.current) !== acknowledged.current) {
          const value = latest.current;
          const serialized = JSON.stringify(value);
          setState("saving"); setFailure(null);
          if (mode === "guest") sessionStorage.setItem(GUEST_KEY, serialized);
          else {
            const row = await api<SavedWizard>("onboarding", { method: "PATCH", body: snapshotBody(value, version.current) });
            version.current = row.version;
          }
          acknowledged.current = serialized;
        }
        setState("saved");
        return true;
      } catch (error) {
        setFailure(error instanceof ApiError ? error.code : "storage_unavailable");
        setState(error instanceof ApiError && error.status === 409 ? "conflict" : error instanceof ApiError && error.unauthenticated ? "expired" : "error");
        return false;
      } finally { inflight.current = null; }
    };
    inflight.current = Promise.resolve().then(operation);
    return inflight.current;
  }, [mode, setState]);

  useEffect(() => {
    if (!ready || ["conflict", "expired"].includes(statusRef.current)) return;
    const timer = window.setTimeout(() => { void flush(); }, 600);
    return () => window.clearTimeout(timer);
  }, [snapshot, ready, flush]);

  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => {
      if (readyRef.current && JSON.stringify(latest.current) !== acknowledged.current) { event.preventDefault(); event.returnValue = ""; }
    };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, []);

  async function importGuest() {
    if (!guest) return;
    change(() => guest);
    if (await flush()) { try { sessionStorage.removeItem(GUEST_KEY); } catch {} setGuest(null); }
  }

  async function complete() {
    if (mode !== "account" || completing.current) return false;
    completing.current = true; setFinishing(true);
    try {
      if (!(await flush())) return false;
      setState("saving");
      const row = await api<SavedWizard>("onboarding/complete", { method: "POST", body: { version: version.current } });
      version.current = row.version;
      latest.current = { ...latest.current, step: row.step };
      acknowledged.current = JSON.stringify(latest.current);
      setSnapshot(latest.current); setCompleted(true); setState("saved");
      return true;
    } catch (error) {
      setFailure(error instanceof ApiError ? error.code : "unavailable");
      setState(error instanceof ApiError && error.status === 409 ? "conflict" : error instanceof ApiError && error.unauthenticated ? "expired" : "error");
      return false;
    } finally { completing.current = false; setFinishing(false); }
  }

  return { finishing, snapshot, change, status, failure, ready, completed, guest, importGuest, flush, reload: load, complete };
}
