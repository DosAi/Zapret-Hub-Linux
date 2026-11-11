import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { getBridge } from "@/bridge";
import { uiAssetUrl } from "@/lib/assets";
import type { UninstallState } from "@/bridge/types";

const isRu = navigator.language.toLowerCase().startsWith("ru");
const L = (ru: string, en: string) => isRu ? ru : en;

export function UninstallPage() {
  const [state, setState] = useState<UninstallState>({ status: "ready" });
  const [removeHapp, setRemoveHapp] = useState(false);
  const [keepData, setKeepData] = useState(true);

  useEffect(() => {
    let active = true;
    window.requestAnimationFrame(() => {
      const hideBoot = (window as Window & { __zapretHideStartupBoot?: () => void }).__zapretHideStartupBoot;
      hideBoot?.();
    });
    void getBridge().call("uninstall.preview", undefined).then((next) => active && setState(next));
    const timer = window.setInterval(() => {
      void getBridge().call("uninstall.status", undefined).then((next) => {
        if (active) setState((current) => ({ ...current, ...next }));
      });
    }, 450);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const running = state.status === "running";
  const done = state.status === "done";

  const start = () => {
    setState((current) => ({ ...current, status: "running", message: "" }));
    void getBridge().call("uninstall.run", { removeHapp, purgeData: !keepData });
  };

  return (
    <div className="grid h-full w-full place-items-center bg-transparent p-[6px]">
      <div className="app-window relative flex h-full w-full flex-col overflow-hidden rounded-[18px] border border-line-1 bg-bg-0">
        <header
          className="window-frame flex h-[50px] shrink-0 items-center justify-between bg-bg-0 px-[14px] select-none"
          onPointerDown={(event) => {
            if (event.button !== 0 || (event.target as HTMLElement).closest("button")) return;
            void getBridge().call("window.startDrag", undefined);
          }}
        >
          <div className="flex items-center gap-2">
            <img src={uiAssetUrl("icons/app.png")} className="h-[22px] w-[22px] object-contain" aria-hidden="true" />
            <span className="brand-font text-[16px] font-semibold text-fg">Zapret Hub</span>
            <span className="text-[12px] text-fg-dim">{L("Удаление", "Uninstall")}</span>
          </div>
          <div className="flex items-center gap-1">
            <button className="grid h-9 w-9 place-items-center rounded-[9px] text-fg-dim hover:bg-bg-3 hover:text-fg" onClick={() => getBridge().call("window.minimize", undefined)} aria-label={L("Свернуть", "Minimize")}>
              <svg width="12" height="12" viewBox="0 0 12 12"><rect x="2" y="6" width="8" height="1" fill="currentColor" /></svg>
            </button>
            <button disabled={running} className="grid h-9 w-9 place-items-center rounded-[9px] text-fg-dim hover:bg-[var(--err)] hover:text-white disabled:opacity-40" onClick={() => getBridge().call("window.close", undefined)} aria-label={L("Закрыть", "Close")}>
              <svg width="12" height="12" viewBox="0 0 12 12" stroke="currentColor" strokeWidth="1.2"><path d="M3 3l6 6M9 3l-6 6" /></svg>
            </button>
          </div>
        </header>

        <main className="content-surface relative flex min-h-0 flex-1 items-center justify-center overflow-hidden bg-bg-1 px-12 py-8">
          <motion.section initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="w-full max-w-[650px]">
            <div className="mb-6 flex items-start gap-4">
              <div className="grid h-12 w-12 shrink-0 place-items-center rounded-[14px] border border-line-2 bg-bg-2 text-warn">
                <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="m7 7 1 13h8l1-13"/><path d="M10 11v5M14 11v5"/></svg>
              </div>
              <div>
                <h1 className="text-[22px] font-semibold tracking-[-0.02em] text-fg">
                  {done ? L("Zapret Hub удалён", "Zapret Hub was removed") : L("Удалить Zapret Hub Linux?", "Remove Zapret Hub Linux?")}
                </h1>
                <p className="mt-1 text-[12px] leading-relaxed text-fg-dim">
                  {done
                    ? L("Системные службы, ярлыки и управляемые компоненты удалены.", "System services, launchers and managed components were removed.")
                    : L("Будут удалены только компоненты, установленные Zapret Hub. Сторонние установки и общие системные пакеты останутся.", "Only components installed by Zapret Hub will be removed. Third-party installations and shared system packages will stay.")}
                </p>
              </div>
            </div>

            {!done && (
              <div className="space-y-3 rounded-[16px] border border-line-1 bg-bg-2 p-4">
                <label className="flex cursor-pointer items-start gap-3 rounded-[12px] p-2 hover:bg-bg-3">
                  <input type="checkbox" checked={keepData} disabled={running} onChange={(event) => setKeepData(event.target.checked)} className="mt-0.5 h-4 w-4 accent-[var(--accent)]" />
                  <span><span className="block text-[13px] font-medium text-fg">{L("Сохранить настройки и логи", "Keep settings and logs")}</span><span className="mt-0.5 block text-[11px] text-fg-dim">{L("Исходная папка проекта также останется на диске.", "The source checkout will also remain on disk.")}</span></span>
                </label>
                <label className="flex cursor-pointer items-start gap-3 rounded-[12px] p-2 hover:bg-bg-3">
                  <input type="checkbox" checked={removeHapp} disabled={running} onChange={(event) => setRemoveHapp(event.target.checked)} className="mt-0.5 h-4 w-4 accent-[var(--accent)]" />
                  <span><span className="block text-[13px] font-medium text-fg">{L("Также удалить Happ", "Also remove Happ")}</span><span className="mt-0.5 block text-[11px] text-fg-dim">{L("Выбирайте только если Happ больше не нужен другим конфигурациям.", "Select this only if Happ is not needed by other configurations.")}</span></span>
                </label>
              </div>
            )}

            {running && <div className="mt-5 h-1 overflow-hidden rounded-full bg-bg-3"><motion.div className="h-full w-1/3 rounded-full bg-accent" animate={{ x: ["-100%", "300%"] }} transition={{ repeat: Infinity, duration: 1.15, ease: "easeInOut" }} /></div>}
            {state.appRunning && !done && <div className="mt-4 rounded-[12px] border border-[color-mix(in_srgb,var(--warn)_45%,transparent)] bg-[color-mix(in_srgb,var(--warn)_10%,transparent)] p-3 text-[11px] text-warn">{L("Сначала полностью закройте основное приложение Zapret Hub. Кнопка удаления станет доступна автоматически.", "Close the main Zapret Hub application first. The Remove button will become available automatically.")}</div>}
            {state.status === "error" && <div className="mt-4 max-h-20 overflow-auto rounded-[12px] border border-[color-mix(in_srgb,var(--err)_45%,transparent)] bg-[color-mix(in_srgb,var(--err)_10%,transparent)] p-3 text-[11px] text-err">{state.message || L("Не удалось завершить удаление.", "Uninstall failed.")}</div>}
            {done && state.projectRoot && <div className="mt-4 rounded-[12px] border border-line-1 bg-bg-2 p-3 text-[11px] text-fg-dim">{L("Папка исходников сохранена:", "Source folder preserved:")} <span className="font-mono text-fg">{state.projectRoot}</span></div>}

            <div className="mt-6 flex justify-end gap-2">
              {!done && <button disabled={running} onClick={() => getBridge().call("window.close", undefined)} className="rounded-[11px] border border-line-1 bg-bg-2 px-4 py-2.5 text-[12px] text-fg-dim hover:bg-bg-3 disabled:opacity-40">{L("Отмена", "Cancel")}</button>}
              {!done && <button disabled={running || state.appRunning} onClick={start} className="rounded-[11px] bg-[var(--err)] px-5 py-2.5 text-[12px] font-semibold text-white hover:brightness-110 disabled:opacity-50">{running ? L("Удаление…", "Removing…") : L("Удалить", "Remove")}</button>}
              {done && <button onClick={() => getBridge().call("window.close", undefined)} className="rounded-[11px] bg-fg px-5 py-2.5 text-[12px] font-semibold text-bg-0 hover:opacity-90">{L("Готово", "Done")}</button>}
            </div>
          </motion.section>
        </main>
      </div>
    </div>
  );
}
