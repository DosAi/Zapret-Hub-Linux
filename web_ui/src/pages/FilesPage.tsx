import { useEffect, useMemo, useState } from "react";
import { useAppState, useBridge } from "@/hooks/useBridgeState";
import { useLocale } from "@/hooks/useLocale";
import { Segmented } from "@/components/ui/Segmented";
import type { FileKind } from "@/bridge/types";
import { useToast } from "@/components/shell/ToastHost";
import { uiAssetUrl } from "@/lib/assets";

const KINDS_CLASSIC: FileKind[] = ["domains", "exclusions", "ip-lists", "ip-exclusions", "general", "hosts", "advanced"];
const KINDS_ZAPRET2: FileKind[] = ["domains", "exclusions", "ip-lists", "advanced", "general", "hosts"];

export function FilesPage({
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
  const toast = useToast();
  const isZapret2 = runtime === "zapret2";
  const kinds = isZapret2 ? KINDS_ZAPRET2 : KINDS_CLASSIC;
  const [kind, setKind] = useState<FileKind>("domains");
  const [buf, setBuf] = useState("");
  const [name, setName] = useState("");
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (!kinds.includes(kind)) setKind(kinds[0]);
  }, [isZapret2]); // eslint-disable-line

  const files = isZapret2 ? (state?.files2 || []) : (state?.files || []);
  const file = useMemo(() => files.find((f) => f.kind === kind), [files, kind]);

  useEffect(() => {
    if (file) { setBuf(file.content); setName(file.name); }
  }, [file?.kind, file?.name, file?.content]); // eslint-disable-line

  const options = kinds.map((k) => ({ value: k, label: t(`files.kind.${k}` as never) }));
  const prefix = isZapret2 ? "files2" : "files";
  const title = isZapret2
    ? (locale === "ru" ? "Файлы Zapret 2" : "Zapret 2 files")
    : t("files.title");
  const desc = isZapret2
    ? (locale === "ru"
      ? "Hostlist / ipset / Lua для winws2 — отдельно от обычного Zapret"
      : "Hostlist / ipset / Lua for winws2 — separate from classic Zapret")
    : t("files.desc");

  const matchCount = useMemo(() => {
    if (!search.trim()) return 0;
    const q = search.toLowerCase();
    return buf.split("\n").filter((line) => line.toLowerCase().includes(q)).length;
  }, [buf, search]);

  const save = async () => {
    if (!file) return;
    const id = toast.push({ message: t("toast.applying") });
    try {
      await bridge.call(`${prefix}.save`, { kind: file.kind, name, content: buf });
      toast.push({ id, message: t("toast.applied"), kind: "success" });
    } catch {
      toast.push({ id, message: locale === "ru" ? "Не удалось сохранить" : "Save failed", kind: "error" });
    }
  };

  const create = async () => {
    const n = prompt("New file name?");
    if (!n) return;
    await bridge.call(`${prefix}.create`, { kind, name: n });
  };

  const rename = async () => {
    if (!file) return;
    const n = prompt("Rename to?", name);
    if (!n) return;
    await bridge.call(`${prefix}.rename`, { kind, from: file.name, to: n });
    setName(n);
  };

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-line-1 px-6 pb-3 pt-5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-2.5">
            {nestedInSettings && <button onClick={onBack} aria-label={isZapret2 ? "Назад к настройкам Zapret 2" : "Назад к настройкам Zapret"} className="icon-button mt-[-2px] grid h-8 w-8 shrink-0 place-items-center rounded-[9px] text-fg-dim hover:bg-bg-3 hover:text-fg"><img src={uiAssetUrl("icons/arrow_left.svg")} className="component-icon-adaptive h-4 w-4" aria-hidden="true" /></button>}
            <div className="min-w-0">
            <h2 className="flex items-center gap-2 text-[15px] font-semibold text-fg">{nestedInSettings && <img src={uiAssetUrl("icons/files.svg")} className="component-icon-adaptive h-4 w-4" aria-hidden="true" />}{title}</h2>
            <p className="mt-0.5 text-[11px] text-fg-dim">{desc}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("files.search")}
              className="h-7 w-32 rounded-lg border border-line-1 bg-bg-1 px-2 text-[11px] text-fg outline-none placeholder:text-fg-mute focus:border-line-2"
            />
            <button onClick={create} className="rounded-lg border border-line-1 bg-bg-1 px-2.5 py-1 text-[11px] text-fg-dim hover:bg-bg-3 hover:text-fg">{t("files.create")}</button>
            <button onClick={rename} className="rounded-lg border border-line-1 bg-bg-1 px-2.5 py-1 text-[11px] text-fg-dim hover:bg-bg-3 hover:text-fg">{t("files.rename")}</button>
            <button onClick={save} className="rounded-lg border border-line-2 bg-bg-3 px-2.5 py-1 text-[11px] text-fg hover:bg-[#1c1c1c]">{t("files.save")}</button>
          </div>
        </div>
        <div className="mt-3 flex items-center justify-between gap-2">
          <Segmented value={kind} onChange={setKind} options={options} size="sm" />
          {search.trim() ? (
            <span className="shrink-0 text-[10px] text-fg-mute">
              {locale === "ru" ? `Совпадений: ${matchCount}` : `Matches: ${matchCount}`}
            </span>
          ) : null}
        </div>
      </div>
      <div className="relative flex-1 overflow-hidden px-6 py-3">
        <textarea
          value={buf}
          onChange={(e) => setBuf(e.target.value)}
          spellCheck={false}
          className="h-full w-full resize-none rounded-xl border border-line-1 bg-bg-1 p-3 font-mono text-[12px] leading-relaxed text-fg outline-none focus:border-line-2"
        />
      </div>
    </div>
  );
}
