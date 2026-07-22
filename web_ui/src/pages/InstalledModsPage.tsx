import { useEffect, useMemo, useState } from "react";
import {
  DndContext,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import { SortableContext, arrayMove, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { getBridge } from "@/bridge";
import { useAppState, useBridge, patchOptimistic } from "@/hooks/useBridgeState";
import { useLocale } from "@/hooks/useLocale";
import { Segmented } from "@/components/ui/Segmented";
import { IosToggle } from "@/components/ui/IosToggle";
import type { MarketplaceCompatibility, Mod } from "@/bridge/types";

type InstalledView = "zapret" | "zapret2";

function ProjectCover({ url, title }: { url?: string; title: string }) {
  const [failed, setFailed] = useState(false);
  if (!url || failed) {
    return (
      <div className="grid h-14 w-14 shrink-0 place-items-center rounded-xl bg-bg-3 text-[13px] font-semibold text-fg-mute">
        {(title.trim()[0] || "?").toUpperCase()}
      </div>
    );
  }
  return (
    <img
      src={url}
      alt=""
      className="h-14 w-14 shrink-0 rounded-xl object-cover"
      onError={() => setFailed(true)}
    />
  );
}

function CompatPill({ value }: { value: MarketplaceCompatibility }) {
  const label = value === "zapret2" ? "Zapret 2" : "Zapret";
  return (
    <span className="rounded-full bg-[color-mix(in_srgb,#9b69e8_28%,transparent)] px-2 py-0.5 text-[10px] font-medium text-[#c4b5fd]">
      {label}
    </span>
  );
}

function SortableLocalCard({
  mod,
  locale,
  compatibility,
  downloading,
  onToggle,
  onUpdate,
  onOpenSite,
  onDelete,
}: {
  mod: Mod;
  locale: string;
  compatibility: MarketplaceCompatibility;
  downloading: boolean;
  onToggle: (on: boolean) => void;
  onUpdate: () => void;
  onOpenSite: () => void;
  onDelete: () => void;
}) {
  const ru = locale === "ru";
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: mod.id });
  const canOpenSite = Boolean(mod.sourceUrl);
  const canUpdate = Boolean(mod.marketplaceSlug && mod.updateAvailable);
  return (
    <article
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.72 : 1 }}
      className="flex items-stretch gap-3 rounded-[14px] border border-line-1 bg-[color-mix(in_srgb,var(--bg-2)_88%,transparent)] px-3.5 py-3"
    >
      <button
        type="button"
        className="mt-1 grid h-8 w-6 shrink-0 cursor-grab place-items-center text-fg-mute active:cursor-grabbing"
        aria-label={ru ? "Перетащить" : "Drag"}
        {...attributes}
        {...listeners}
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
          <circle cx="8" cy="6" r="1.5" />
          <circle cx="8" cy="12" r="1.5" />
          <circle cx="8" cy="18" r="1.5" />
          <circle cx="16" cy="6" r="1.5" />
          <circle cx="16" cy="12" r="1.5" />
          <circle cx="16" cy="18" r="1.5" />
        </svg>
      </button>
      <ProjectCover url={mod.iconUrl} title={mod.name} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <h3 className="truncate text-[13px] font-semibold text-fg">{mod.name}</h3>
          {mod.author ? (
            <span className="truncate text-[11px] text-fg-mute">
              {ru ? "от" : "by"} @{mod.author.replace(/^@/, "")}
            </span>
          ) : null}
        </div>
        <p className="mt-0.5 line-clamp-2 text-[11px] text-fg-dim">{mod.description || "—"}</p>
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          <CompatPill value={compatibility} />
          {mod.version ? <span className="rounded-full bg-bg-3 px-2 py-0.5 text-[10px] text-fg-dim">v{mod.version}</span> : null}
          {canUpdate ? (
            <span className="rounded-full bg-[color-mix(in_srgb,rgb(var(--page-accent-rgb))_22%,transparent)] px-2 py-0.5 text-[10px] text-[rgb(var(--page-accent-rgb))]">
              {ru ? `есть v${mod.latestVersion}` : `v${mod.latestVersion} available`}
            </span>
          ) : null}
        </div>
      </div>
      <div className="flex shrink-0 flex-col items-end justify-between gap-2 pl-1">
        <IosToggle on={mod.enabled} onChange={onToggle} />
        <div className="flex flex-wrap items-center justify-end gap-1">
          {canUpdate ? (
            <button
              type="button"
              disabled={downloading}
              onClick={onUpdate}
              className="rounded-md bg-[rgb(var(--page-accent-rgb))] px-2 py-0.5 text-[10px] font-medium text-white disabled:opacity-50"
            >
              {downloading ? "…" : ru ? "Обновить" : "Update"}
            </button>
          ) : null}
          {canOpenSite ? (
            <button type="button" onClick={onOpenSite} className="rounded-md px-1.5 py-0.5 text-[10px] text-fg-mute hover:bg-bg-3 hover:text-fg">
              {ru ? "На сайте" : "Website"}
            </button>
          ) : null}
          <button type="button" onClick={onDelete} className="rounded-md px-1.5 py-0.5 text-[10px] text-fg-mute hover:bg-bg-3 hover:text-[var(--err)]">
            {ru ? "Удалить" : "Delete"}
          </button>
        </div>
      </div>
    </article>
  );
}

function isMarketplaceMod(mod: Mod) {
  return Boolean(String(mod.marketplaceSlug || "").trim());
}

export function InstalledModsPage({ onOpenMarketplace }: { onOpenMarketplace?: () => void }) {
  const bridge = useBridge();
  const state = useAppState();
  const { locale } = useLocale();
  const ru = locale === "ru";
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));
  const [view, setView] = useState<InstalledView>("zapret");
  const [queued, setQueued] = useState<Set<string>>(new Set());

  useEffect(() => {
    const off = getBridge().subscribe("marketplace.download-progress", (payload) => {
      const slug = String(payload?.slug || "");
      const status = String(payload?.status || "");
      if (!slug) return;
      setQueued((prev) => {
        const next = new Set(prev);
        if (status === "queued" || status === "starting" || status === "downloading" || status === "installing") {
          next.add(slug);
        } else {
          next.delete(slug);
        }
        return next;
      });
    });
    return off;
  }, []);

  useEffect(() => {
    void bridge.call("marketplace.check-updates", undefined).catch(() => undefined);
  }, [bridge]);

  const installedZapret = useMemo(
    () =>
      (state?.mods || []).filter(
        (m) => isMarketplaceMod(m) && m.id.toLowerCase() !== "hub" && m.name.trim().toLowerCase() !== "hub",
      ),
    [state?.mods],
  );
  const installedZapret2 = useMemo(
    () => (state?.mods2 || []).filter((m) => isMarketplaceMod(m)),
    [state?.mods2],
  );

  const list = view === "zapret2" ? installedZapret2 : installedZapret;
  const prefix = view === "zapret2" ? "mods2" : "mods";
  const compatibility: MarketplaceCompatibility = view === "zapret2" ? "zapret2" : "zapret";

  const onDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const ids = list.map((m) => m.id);
    const oldIndex = ids.indexOf(String(active.id));
    const newIndex = ids.indexOf(String(over.id));
    if (oldIndex < 0 || newIndex < 0) return;
    void bridge.call(`${prefix}.reorder`, { orderedIds: arrayMove(ids, oldIndex, newIndex) });
  };

  const enqueue = async (mod: Mod) => {
    if (!mod.marketplaceSlug) return;
    setQueued((prev) => new Set(prev).add(mod.marketplaceSlug!));
    try {
      await bridge.call("marketplace.download", {
        slug: mod.marketplaceSlug,
        title: mod.name,
        compatibility,
        author: mod.author,
        summary: mod.description,
        iconUrl: mod.iconUrl,
        projectUrl: mod.sourceUrl,
      });
    } catch {
      setQueued((prev) => {
        const next = new Set(prev);
        next.delete(mod.marketplaceSlug!);
        return next;
      });
    }
  };

  return (
    <div className="relative flex h-full flex-col">
      <div className="border-b border-line-1 px-6 pb-3 pt-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-[15px] font-semibold text-fg">{ru ? "Установленные модификации" : "Installed mods"}</h2>
            <p className="mt-0.5 text-[11px] text-fg-dim">
              {ru
                ? "Модификации, установленные из Zapret Marketplace"
                : "Mods installed from Zapret Marketplace"}
            </p>
          </div>
          <Segmented
            value={view}
            onChange={setView}
            size="sm"
            options={[
              { value: "zapret", label: ru ? "Zapret" : "Zapret" },
              { value: "zapret2", label: "Zapret 2" },
            ]}
          />
        </div>
      </div>

      <div className="scroll-area min-h-0 flex-1 overflow-auto px-6 py-3">
        {list.length === 0 ? (
          <div className="grid h-40 place-content-center justify-items-center gap-3 text-center">
            <p className="text-[12px] text-fg-mute">
              {ru ? "Пока нет модификаций…" : "No mods yet…"}
            </p>
            <button
              type="button"
              onClick={() => onOpenMarketplace?.()}
              className="rounded-lg bg-[rgb(var(--page-accent-rgb))] px-3.5 py-1.5 text-[11px] font-medium text-white transition hover:brightness-110"
            >
              {ru ? "Добавить" : "Add"}
            </button>
          </div>
        ) : (
          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
            <SortableContext items={list.map((m) => m.id)} strategy={verticalListSortingStrategy}>
              <div className="flex flex-col gap-2.5">
                {list.map((mod) => (
                  <SortableLocalCard
                    key={mod.id}
                    mod={mod}
                    locale={locale}
                    compatibility={compatibility}
                    downloading={Boolean(mod.marketplaceSlug && queued.has(mod.marketplaceSlug))}
                    onToggle={(on) => {
                      if (prefix === "mods2") {
                        patchOptimistic({ mods2: { [mod.id]: { enabled: on } } });
                      } else {
                        patchOptimistic({ mods: { [mod.id]: { enabled: on } } });
                      }
                      void bridge.call(`${prefix}.toggle`, { id: mod.id, on });
                    }}
                    onUpdate={() => void enqueue(mod)}
                    onOpenSite={() => {
                      if (mod.sourceUrl) void bridge.call("marketplace.open-url", { url: mod.sourceUrl });
                    }}
                    onDelete={() => {
                      if (!window.confirm(ru ? `Удалить «${mod.name}»?` : `Delete “${mod.name}”?`)) return;
                      void bridge.call(`${prefix}.delete`, { id: mod.id });
                    }}
                  />
                ))}
              </div>
            </SortableContext>
          </DndContext>
        )}
      </div>
    </div>
  );
}
