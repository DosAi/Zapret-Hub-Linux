import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { useLocale } from "@/hooks/useLocale";
import { useBridge } from "@/hooks/useBridgeState";
import { MarkdownContent } from "@/components/ui/MarkdownContent";

export type AppUpdatePrompt = {
  currentVersion: string;
  latestVersion: string;
  changelog: string;
  htmlUrl: string;
  isHotfix?: boolean;
  demo?: boolean;
};

export function AppUpdateModal({
  prompt,
  onClose,
}: {
  prompt: AppUpdatePrompt | null;
  onClose: () => void;
}) {
  const { locale } = useLocale();
  const bridge = useBridge();
  const ru = locale === "ru";
  const [busy, setBusy] = useState(false);

  const applyNow = async () => {
    if (!prompt || prompt.demo || busy) {
      onClose();
      return;
    }
    setBusy(true);
    try {
      await bridge.call("app.apply-update", { scheduleNextLaunch: false });
      // App should quit for overlay install; keep modal until then.
    } catch {
      setBusy(false);
    }
  };

  const scheduleNext = async () => {
    if (!prompt || prompt.demo || busy) {
      onClose();
      return;
    }
    setBusy(true);
    try {
      await bridge.call("app.apply-update", { scheduleNextLaunch: true });
      onClose();
    } catch {
      setBusy(false);
    }
  };

  return (
    <AnimatePresence>
      {prompt && (
        <motion.div
          key="app-update-modal"
          className="absolute inset-0 z-[90] grid place-items-center bg-black/46"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={() => { if (!busy) onClose(); }}
        >
          <motion.div
            initial={{ opacity: 0, y: 8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 6, scale: 0.98 }}
            transition={{ duration: 0.18 }}
            onClick={(event) => event.stopPropagation()}
            className="flex w-[520px] max-w-[92%] flex-col overflow-hidden rounded-[16px] border border-line-2 bg-bg-2 shadow-[0_18px_42px_-20px_rgba(0,0,0,0.75)]"
          >
            <header className="flex h-12 items-center justify-between border-b border-line-1 px-4">
              <div className="text-[13px] font-semibold text-fg">
                {prompt.isHotfix
                  ? (ru ? "Обнаружен hotfix" : "Hotfix available")
                  : (ru ? "Доступно обновление" : "Update available")}
              </div>
              <button type="button" disabled={busy} onClick={onClose} className="grid h-7 w-7 place-items-center rounded-[8px] text-fg-dim hover:bg-bg-3 hover:text-fg disabled:opacity-40">×</button>
            </header>
            <div className="space-y-3 px-4 py-3">
              <p className="whitespace-pre-line text-[12px] leading-relaxed text-fg-dim">
                {prompt.isHotfix
                  ? (ru
                    ? `Для Zapret Hub ${prompt.currentVersion} найден hotfix.\nHotfix — необязательное обновление, но оно может содержать важные исправления, поэтому настоятельно рекомендуем обновиться.`
                    : `A hotfix is available for Zapret Hub ${prompt.currentVersion}.\nA hotfix is optional, but it may contain important fixes, so updating is strongly recommended.`)
                  : (ru
                    ? `Вышла новая версия Zapret Hub.\nТекущая: ${prompt.currentVersion} · Новая: ${prompt.latestVersion}`
                    : `A new Zapret Hub version is available.\nCurrent: ${prompt.currentVersion} · New: ${prompt.latestVersion}`)}
              </p>
              <MarkdownContent className="max-h-[180px] overflow-y-auto rounded-[12px] border border-line-1 bg-bg-1 p-3 text-[11px] leading-relaxed text-fg-dim">
                {prompt.changelog || (ru ? "Список изменений недоступен." : "Changelog is unavailable.")}
              </MarkdownContent>
              {prompt.demo && (
                <div className="rounded-[10px] border border-line-1 bg-bg-3/60 px-3 py-2 text-[10px] text-fg-mute">
                  {ru ? "Тестовый показ интерфейса обновления (один раз)." : "One-time demo of the update UI."}
                </div>
              )}
              {busy && (
                <div className="text-[11px] text-fg-dim">
                  {ru ? "Скачиваем и готовим обновление…" : "Downloading and preparing the update…"}
                </div>
              )}
            </div>
            <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-line-1 px-4 py-3">
              <button type="button" disabled={busy} onClick={onClose} className="rounded-[9px] border border-line-1 bg-bg-1 px-3 py-1.5 text-[11px] text-fg-dim hover:bg-bg-3 hover:text-fg disabled:opacity-40">
                {ru ? "Закрыть" : "Close"}
              </button>
              {prompt.htmlUrl && (
                <a
                  href={prompt.htmlUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-[9px] border border-line-1 bg-bg-2 px-3 py-1.5 text-[11px] text-fg hover:bg-bg-3"
                >
                  {ru ? "Открыть ссылку" : "Open link"}
                </a>
              )}
              {!prompt.demo && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void scheduleNext()}
                  className="rounded-[9px] border border-line-1 bg-bg-1 px-3 py-1.5 text-[11px] text-fg-dim hover:bg-bg-3 hover:text-fg disabled:opacity-40"
                >
                  {ru ? "При следующем запуске" : "On next launch"}
                </button>
              )}
              <button
                type="button"
                disabled={busy}
                onClick={() => void applyNow()}
                className="rounded-[9px] border border-line-2 bg-fg px-3 py-1.5 text-[11px] font-medium text-bg-0 hover:opacity-90 disabled:opacity-40"
              >
                {ru ? "Обновить сейчас" : "Update now"}
              </button>
            </footer>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
