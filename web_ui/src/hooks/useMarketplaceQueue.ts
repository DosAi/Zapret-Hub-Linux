import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { getBridge } from "@/bridge";
import type { MarketplaceQueueItem, MarketplaceQueueStatus } from "@/bridge/types";
import { applyMarketplaceMods, refreshMarketplaceMods } from "@/hooks/useBridgeState";

const EMPTY: MarketplaceQueueStatus = {
  busy: false,
  activeSlug: "",
  overallProgress: 0,
  pending: [],
  items: [],
};

type Store = {
  queue: MarketplaceQueueStatus;
  completedFlash: boolean;
};

let store: Store = { queue: EMPTY, completedFlash: false };
const listeners = new Set<() => void>();
let wired = false;
let flashTimer: number | undefined;

function emitStore() {
  for (const listener of listeners) listener();
}

function setStore(next: Partial<Store>) {
  store = { ...store, ...next };
  emitStore();
}

function normalize(status: Partial<MarketplaceQueueStatus> | null | undefined): MarketplaceQueueStatus {
  const items = Array.isArray(status?.items) ? status!.items : [];
  return {
    busy: Boolean(status?.busy),
    activeSlug: String(status?.activeSlug || ""),
    overallProgress: Number(status?.overallProgress || 0),
    pending: Array.isArray(status?.pending) ? status!.pending.map(String) : items.map((i) => i.slug),
    items,
  };
}

function applyQueue(next: MarketplaceQueueStatus) {
  const hadActive = store.queue.items.length > 0 || store.queue.busy;
  const idle = next.items.length === 0 && !next.busy;
  if (hadActive && idle) {
    setStore({ queue: next, completedFlash: true });
    window.clearTimeout(flashTimer);
    flashTimer = window.setTimeout(() => setStore({ completedFlash: false }), 3200);
    return;
  }
  if (!idle && store.completedFlash) {
    window.clearTimeout(flashTimer);
    setStore({ queue: next, completedFlash: false });
    return;
  }
  setStore({ queue: next });
}

let pollTimer: number | undefined;

function pollQueueOnce() {
  const bridge = getBridge();
  void bridge
    .call("marketplace.queue", undefined)
    .then((result) => applyQueue(normalize(result)))
    .catch(() => undefined);
}

function armQueuePoll() {
  if (typeof window === "undefined") return;
  if (pollTimer != null) return;
  // bridgeEvent/subscribe can miss updates in WebEngine — poll while work is active.
  pollTimer = window.setInterval(() => {
    const busy =
      store.queue.busy ||
      store.queue.items.some((item) =>
        ["queued", "downloading", "paused", "installing", "starting"].includes(String(item.status || "")),
      );
    if (!busy) {
      window.clearInterval(pollTimer);
      pollTimer = undefined;
      return;
    }
    pollQueueOnce();
  }, 1000);
}

function ensureWired() {
  if (wired || typeof window === "undefined") return;
  wired = true;
  const bridge = getBridge();
  pollQueueOnce();
  bridge.subscribe("marketplace.queue", (payload) => {
    applyQueue(normalize(payload));
    armQueuePoll();
  });
  bridge.subscribe("marketplace.download-progress", (payload) => {
    const slug = String(payload?.slug || "");
    const status = String(payload?.status || "");
    if (!slug) return;
    const items = [...store.queue.items];
    const idx = items.findIndex((item) => item.slug === slug || (payload.jobId && item.jobId === payload.jobId));
    const nextItem: MarketplaceQueueItem = {
      jobId: String(payload.jobId || (idx >= 0 ? items[idx].jobId : slug)),
      slug,
      status,
      message: payload.message,
      title: payload.title || (idx >= 0 ? items[idx].title : slug),
      iconUrl: payload.iconUrl || (idx >= 0 ? items[idx].iconUrl : ""),
      compatibility: payload.compatibility || (idx >= 0 ? items[idx].compatibility : ""),
      progress: Number(payload.progress ?? (idx >= 0 ? items[idx].progress : 0) ?? 0),
      bytesDone: Number(payload.bytesDone ?? (idx >= 0 ? items[idx].bytesDone : 0) ?? 0),
      bytesTotal: Number(payload.bytesTotal ?? (idx >= 0 ? items[idx].bytesTotal : 0) ?? 0),
      error: payload.error,
    };
    if (status === "done" || status === "error" || status === "cancelled") {
      if (idx >= 0) items.splice(idx, 1);
      if (status === "done") {
        if (Array.isArray(payload.mods) && Array.isArray(payload.mods2)) {
          applyMarketplaceMods(payload.mods, payload.mods2);
        } else {
          void refreshMarketplaceMods(slug).catch(() => undefined);
        }
      }
    } else if (idx >= 0) {
      items[idx] = { ...items[idx], ...nextItem };
    } else {
      items.push(nextItem);
    }
    const busy = items.some((item) => item.status === "downloading" || item.status === "installing" || item.status === "starting");
    const active = items.find((item) => item.status === "downloading" || item.status === "installing" || item.status === "starting");
    const overall = active?.bytesTotal
      ? Math.max(0, Math.min(1, (active.bytesDone || 0) / active.bytesTotal))
      : active
        ? Math.max(0.02, Number(active.progress || 0.02))
        : items.length
          ? 0.02
          : 0;
    applyQueue({
      busy,
      activeSlug: active?.slug || "",
      overallProgress: overall,
      pending: items.map((item) => item.slug),
      items,
    });
    if (busy || items.length > 0) armQueuePoll();
  });
}

function subscribe(listener: () => void) {
  ensureWired();
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot() {
  return store;
}

export function useMarketplaceQueue() {
  const snap = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  const bySlug = useMemo(() => {
    const map = new Map<string, MarketplaceQueueItem>();
    for (const item of snap.queue.items) map.set(item.slug, item);
    return map;
  }, [snap.queue.items]);

  const visible = snap.queue.items.length > 0 || snap.queue.busy || snap.completedFlash;
  const progress = snap.completedFlash ? 1 : Math.max(0, Math.min(1, Number(snap.queue.overallProgress || 0)));

  const cancel = useCallback(async (slug: string, jobId?: string) => {
    applyQueue({
      ...store.queue,
      items: store.queue.items.filter((item) => !(item.slug === slug || (jobId && item.jobId === jobId))),
      pending: store.queue.pending.filter((entry) => entry !== slug),
    });
    const result = await getBridge().call("marketplace.cancel", { slug, jobId });
    applyQueue(normalize(result));
  }, []);

  const pause = useCallback(async (slug: string, jobId?: string) => {
    applyQueue({
      ...store.queue,
      items: store.queue.items.map((item) =>
        item.slug === slug || (jobId && item.jobId === jobId) ? { ...item, status: "paused", message: "paused" } : item,
      ),
    });
    const result = await getBridge().call("marketplace.pause", { slug, jobId });
    applyQueue(normalize(result));
  }, []);

  const resume = useCallback(async (slug: string, jobId?: string) => {
    applyQueue({
      ...store.queue,
      items: store.queue.items.map((item) =>
        item.slug === slug || (jobId && item.jobId === jobId) ? { ...item, status: "queued", message: item.title || item.slug } : item,
      ),
    });
    const result = await getBridge().call("marketplace.resume", { slug, jobId });
    applyQueue(normalize(result));
  }, []);

  const reorder = useCallback(async (orderedSlugs: string[]) => {
    const result = await getBridge().call("marketplace.reorder-queue", { orderedSlugs });
    applyQueue(normalize(result));
  }, []);

  const enqueue = useCallback(
    async (item: {
      slug: string;
      title?: string;
      compatibility?: string;
      versionId?: number | null;
      author?: string;
      summary?: string;
      iconUrl?: string;
      projectUrl?: string;
    }) => {
      if (!store.queue.items.some((entry) => entry.slug === item.slug)) {
        applyQueue({
          ...store.queue,
          busy: store.queue.busy || store.queue.items.length === 0,
          pending: [...store.queue.pending, item.slug],
          items: [
            ...store.queue.items,
            {
              jobId: `local-${item.slug}`,
              slug: item.slug,
              status: "queued",
              title: item.title || item.slug,
              iconUrl: item.iconUrl || "",
              compatibility: item.compatibility || "",
              progress: 0,
              bytesDone: 0,
              bytesTotal: 0,
            },
          ],
        });
      }
      try {
        const result = await getBridge().call("marketplace.download", {
          slug: item.slug,
          title: item.title,
          compatibility: item.compatibility,
          versionId: item.versionId ?? null,
          author: item.author,
          summary: item.summary,
          iconUrl: item.iconUrl,
          projectUrl: item.projectUrl,
        });
        armQueuePoll();
        const snapQueue = await getBridge().call("marketplace.queue", undefined);
        applyQueue(normalize(snapQueue));
        return result;
      } catch (error) {
        applyQueue({
          ...store.queue,
          items: store.queue.items.filter((entry) => entry.slug !== item.slug),
          pending: store.queue.pending.filter((slug) => slug !== item.slug),
        });
        throw error;
      }
    },
    [],
  );

  // Keep hook reactive even if no components subscribed yet when first import happens in SSR-less env.
  useEffect(() => {
    ensureWired();
  }, []);

  return {
    queue: snap.queue,
    bySlug,
    visible,
    progress,
    completedFlash: snap.completedFlash,
    cancel,
    pause,
    resume,
    reorder,
    enqueue,
  };
}
