import { useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useAppState, useBridge, patchOptimistic } from "@/hooks/useBridgeState";
import { useLocale } from "@/hooks/useLocale";
import { IosToggle } from "@/components/ui/IosToggle";
import type { Mod } from "@/bridge/types";
import { uiAssetUrl } from "@/lib/assets";
import { ScrollGlassHeader } from "@/components/ui/ScrollGlassHeader";

export function ModsPage({
  nestedInSettings = false,
  onBack,
  runtime = "zapret",
}: {
  nestedInSettings?: boolean;
  onBack?: () => void;
  runtime?: "zapret" | "zapret2";
}) {
  const state = useAppState();
  const bridge = useBridge();
  const { t, locale } = useLocale();
  const [importOpen, setImportOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const scrollerRef = useRef<HTMLDivElement>(null);
  if (!state) return null;

  const isZapret2 = runtime === "zapret2";
  const prefix = isZapret2 ? "mods2" : "mods";
  const list = isZapret2 ? (state.mods2 || []) : state.mods;
  // Custom mods only — Marketplace installs live on the Installed sidebar page.
  const visibleMods = list.filter(
    (m) =>
      m.id.toLowerCase() !== "hub"
      && m.name.trim().toLowerCase() !== "hub"
      && !String(m.marketplaceSlug || "").trim(),
  );
  const title = isZapret2
    ? (locale === "ru" ? "Пользовательские модификации Zapret 2" : "Custom Zapret 2 modifications")
    : t("mods.title");
  const desc = isZapret2
    ? (locale === "ru"
      ? "Свои наборы правил и Lua для Zapret 2 (не из Marketplace)"
      : "Your own rule packs and Lua for Zapret 2 (not from Marketplace)")
    : t("mods.desc");

  const doImport = (src: Mod["source"]) => {
    if (src === "github" && isZapret2) return;
    const ref = src === "github" ? prompt("Ссылка на GitHub-репозиторий")?.trim() : undefined;
    if (src === "github" && !ref) return;
    bridge.call(`${prefix}.import`, { source: src, ref });
    setImportOpen(false);
  };

  return (
    <div className="relative h-full overflow-hidden">
      <div ref={scrollerRef} className="scroll-area h-full overflow-auto">
      <div className="scroll-content px-7 pb-7 pt-[86px]">
        {visibleMods.length === 0 ? (
          <div className="grid h-32 place-items-center rounded-xl border border-dashed border-line-1 text-[12px] text-fg-mute">
            {t("mods.empty")}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            {visibleMods.map((m) => (
              <div key={m.id} className="flex flex-col rounded-xl border border-line-1 bg-bg-1 p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate text-[13px] font-semibold text-fg">{m.name}</div>
                    {m.author && <div className="text-[10px] text-fg-mute">{m.author}</div>}
                  </div>
                  <IosToggle on={m.enabled} onChange={(v) => {
                    if (isZapret2) {
                      patchOptimistic({ mods2: { [m.id]: { enabled: v } } });
                    } else {
                      patchOptimistic({ mods: { [m.id]: { enabled: v } } });
                    }
                    void bridge.call(`${prefix}.toggle`, { id: m.id, on: v });
                  }} />
                </div>
                {m.description && <div className="mt-2 line-clamp-2 text-[11px] text-fg-dim">{m.description}</div>}
                <div className="mt-3 flex flex-wrap gap-1">
                  {m.compatibleFiles.map((f) => (
                    <span key={f} className="rounded-md border border-line-1 px-1.5 py-0.5 text-[10px] text-fg-mute">{f}</span>
                  ))}
                </div>
                <div className="mt-3 flex items-center justify-between text-[10px] text-fg-mute">
                  <span>{m.source}</span>
                  <div className="flex items-center gap-1">
                    <button onClick={() => bridge.call(`${prefix}.edit`, { id: m.id, patch: {} })} className="rounded-md px-1.5 py-0.5 hover:bg-bg-3 hover:text-fg">{t("mods.edit")}</button>
                    <button onClick={() => bridge.call(`${prefix}.export`, { id: m.id })} className="rounded-md px-1.5 py-0.5 hover:bg-bg-3 hover:text-fg">{t("mods.export")}</button>
                    <button onClick={() => bridge.call(`${prefix}.delete`, { id: m.id })} className="rounded-md px-1.5 py-0.5 hover:bg-bg-3 hover:text-[var(--err)]">{t("mods.delete")}</button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      </div>
      <ScrollGlassHeader scrollerRef={scrollerRef} className="absolute inset-x-0 top-0 z-20 border-b border-line-1 px-7 pb-4 pt-5" foregroundClassName="flex items-start justify-between">
        <div className="flex items-start gap-2.5">
          {nestedInSettings && <button onClick={onBack} aria-label={isZapret2 ? "Назад к настройкам Zapret 2" : "Назад к настройкам Zapret"} className="icon-button mt-[-2px] grid h-8 w-8 place-items-center rounded-[9px] text-fg-dim hover:bg-bg-3 hover:text-fg"><img src={uiAssetUrl("icons/arrow_left.svg")} className="component-icon-adaptive h-4 w-4" aria-hidden="true" /></button>}
          <div>
          <h2 className="flex items-center gap-2 text-[15px] font-semibold text-fg">{nestedInSettings && <img src={uiAssetUrl("icons/mods.svg")} className="component-icon-adaptive h-4 w-4" aria-hidden="true" />}{title}</h2>
          <p className="mt-0.5 text-[11px] text-fg-dim">{desc}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <input
            value={createName}
            onChange={(e) => setCreateName(e.target.value)}
            placeholder={t("common.name")}
            className="h-7 w-32 rounded-lg border border-line-1 bg-bg-1 px-2 text-[11px] text-fg outline-none placeholder:text-fg-mute focus:border-line-2"
          />
          <button
            disabled={!createName.trim()}
            onClick={() => { bridge.call(`${prefix}.create`, { name: createName.trim() }); setCreateName(""); }}
            className="rounded-lg border border-line-1 bg-bg-1 px-2.5 py-1 text-[11px] text-fg-dim hover:bg-bg-3 hover:text-fg disabled:opacity-40"
          >
            {t("mods.create")}
          </button>
          <button
            onClick={() => setImportOpen(true)}
            className="rounded-lg border border-line-1 bg-bg-1 px-2.5 py-1 text-[11px] text-fg hover:bg-bg-3"
          >
            {t("mods.import")}
          </button>
        </div>
      </ScrollGlassHeader>
      <AnimatePresence>
        {importOpen && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.12 }}
            className="absolute inset-0 z-30 grid place-items-center bg-black/50"
            onClick={() => setImportOpen(false)}
          >
            <motion.div
              initial={{ scale: 0.96, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.96, opacity: 0 }}
              transition={{ duration: 0.15 }}
              onClick={(e) => e.stopPropagation()}
              className="w-72 rounded-xl border border-line-2 bg-bg-2 p-3"
            >
              <div className="mb-2 text-[12px] font-medium text-fg">{t("mods.import")}</div>
              <div className="grid grid-cols-2 gap-2">
                {(isZapret2 ? (["folder", "zip", "files"] as const) : (["folder", "zip", "files", "github"] as const)).map((s) => (
                  <button
                    key={s}
                    onClick={() => doImport(s)}
                    className="rounded-lg border border-line-1 bg-bg-1 px-3 py-2 text-[12px] text-fg hover:bg-bg-3"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
