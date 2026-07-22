from __future__ import annotations

from pathlib import Path
import shutil

from zapret_hub.services.service_rules import SERVICE_RULES


LIST_HUB = "list-hub.txt"
LIST_AUTO = "list-auto.txt"
LIST_EXCLUDE = "list-exclude.txt"
IPSET_HUB = "ipset-hub.txt"
LUA_ORCHESTRATOR = "hub-orchestrator.lua"
LUA_STRATEGY = "hub-strategy.lua"
LUA_TARGETS = "hub-targets.lua"

# Curated strategy ids — rewritten into hub-strategy.lua; winws2 restart required.
STRATEGY_IDS = ("balanced", "fake_heavy", "multisplit")

# Seed lists adapted from Downloads/bypass-youtube-discord.lua (FluxRoute → Goshkow).
# In real winws2 filtering uses hostlist/ipset files; Lua keeps the same catalog for docs/sync.
BYPASS_SEED_DOMAINS: tuple[str, ...] = (
    # Discord
    "discord.com",
    "discordapp.com",
    "discord.gg",
    "discord.media",
    "discordcdn.com",
    "discordstatus.com",
    "cdn.discordapp.com",
    "media.discordapp.net",
    "gateway.discord.gg",
    "images-ext-1.discordapp.net",
    "images-ext-2.discordapp.net",
    "dl.discordapp.net",
    "status.discord.com",
    "latency.discord.media",
    "updates.discord.com",
    # YouTube / Google video
    "youtube.com",
    "youtu.be",
    "ytimg.com",
    "googlevideo.com",
    "youtube-nocookie.com",
    "ggpht.com",
    "gvt1.com",
    "youtube.googleapis.com",
    "youtubei.googleapis.com",
    "yt3.googleusercontent.com",
    "manifest.googlevideo.com",
    "redirector.googlevideo.com",
    # From the sample script (optional extras)
    "instagram.com",
    "cdninstagram.com",
    "twitch.tv",
    "jtvnw.net",
    "telegram.org",
    "t.me",
    "web.telegram.org",
    "tiktok.com",
    "tiktokcdn.com",
)

BYPASS_SEED_NETWORKS: tuple[str, ...] = (
    "149.154.167.0/24",  # Telegram
    "173.194.0.0/16",  # Google/YouTube
    "162.159.128.0/20",  # Discord (Cloudflare)
)

_HUB_ORCHESTRATOR_LUA = r'''--[[
  Zapret Hub orchestrator Lua for winws2 (bol-van zapret2).
  Domain/IP catalogs mirror bypass-youtube-discord.lua; actual matching uses
  --hostlist / --ipset files that Hub rewrites (auto-reload, no restart).
  Strategy knobs come from hub-strategy.lua (HUB_STRATEGY).
]]

local function _strategy()
  return (HUB_STRATEGY and tostring(HUB_STRATEGY)) or "balanced"
end

local function _ensure_arg(desync)
  if type(desync.arg) ~= "table" then
    desync.arg = {}
  end
  return desync.arg
end

function hub_tls(ctx, desync)
  local arg = _ensure_arg(desync)
  local s = _strategy()
  if s == "fake_heavy" then
    arg.blob = arg.blob or "fake_default_tls"
    arg.tcp_md5 = true
    arg.repeats = arg.repeats or 11
    arg.tls_mod = arg.tls_mod or "rnd,dupsid,rndsni"
    return fake(ctx, desync)
  elseif s == "multisplit" then
    arg.pos = arg.pos or "1"
    arg.seqovl = arg.seqovl or "5"
    arg.seqovl_pattern = arg.seqovl_pattern or "0x1603030000"
    return multisplit(ctx, desync)
  end
  arg.blob = arg.blob or "fake_default_tls"
  arg.tcp_md5 = true
  arg.tls_mod = arg.tls_mod or "rnd,rndsni,dupsid"
  return fake(ctx, desync)
end

function hub_tls_b(ctx, desync)
  local arg = _ensure_arg(desync)
  local s = _strategy()
  if s == "fake_heavy" then
    arg.pos = arg.pos or "1,midsld"
    return multidisorder(ctx, desync)
  elseif s == "multisplit" then
    arg.blob = arg.blob or "fake_default_tls"
    arg.tcp_md5 = true
    arg.tls_mod = arg.tls_mod or "rnd,dupsid"
    return fake(ctx, desync)
  end
  arg.pos = arg.pos or "1"
  arg.seqovl = arg.seqovl or "5"
  arg.seqovl_pattern = arg.seqovl_pattern or "0x1603030000"
  return multisplit(ctx, desync)
end

function hub_http(ctx, desync)
  local arg = _ensure_arg(desync)
  local s = _strategy()
  if s == "fake_heavy" then
    arg.blob = arg.blob or "fake_default_http"
    arg.tcp_md5 = true
    arg.repeats = arg.repeats or 6
    return fake(ctx, desync)
  elseif s == "multisplit" then
    arg.pos = arg.pos or "1"
    return multisplit(ctx, desync)
  end
  arg.blob = arg.blob or "fake_default_http"
  arg.tcp_md5 = true
  return fake(ctx, desync)
end

function hub_http_b(ctx, desync)
  local arg = _ensure_arg(desync)
  if _strategy() == "fake_heavy" then
    arg.tcp_md5 = true
    return fakedsplit(ctx, desync)
  end
  arg.blob = arg.blob or "fake_default_http"
  arg.tcp_md5 = true
  return fake(ctx, desync)
end

function hub_quic(ctx, desync)
  local arg = _ensure_arg(desync)
  local s = _strategy()
  arg.blob = arg.blob or "fake_default_quic"
  if s == "fake_heavy" then
    arg.repeats = arg.repeats or 11
  elseif s == "multisplit" then
    arg.repeats = arg.repeats or 6
  end
  return fake(ctx, desync)
end

function hub_discord(ctx, desync)
  local arg = _ensure_arg(desync)
  arg.blob = arg.blob or "0x00000000000000000000000000000000"
  arg.repeats = arg.repeats or 2
  return fake(ctx, desync)
end
'''


def zapret2_lists_dir(configs_dir: Path) -> Path:
    return Path(configs_dir) / "zapret2"


def ensure_zapret2_lists(configs_dir: Path) -> dict[str, Path]:
    root = zapret2_lists_dir(configs_dir)
    root.mkdir(parents=True, exist_ok=True)
    paths = {
        "hub": root / LIST_HUB,
        "auto": root / LIST_AUTO,
        "exclude": root / LIST_EXCLUDE,
        "ipset": root / IPSET_HUB,
        "lua_orch": root / LUA_ORCHESTRATOR,
        "lua_strategy": root / LUA_STRATEGY,
        "lua_targets": root / LUA_TARGETS,
    }
    for key in ("hub", "auto", "exclude", "ipset"):
        path = paths[key]
        if not path.exists():
            path.write_text("", encoding="utf-8")
    write_hub_orchestrator_lua(paths["lua_orch"])
    write_hub_targets_lua(paths["lua_targets"])
    return paths


def _list_entries(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return set()
    return {
        row.strip().lower()
        for row in lines
        if row.strip() and not row.lstrip().startswith("#")
    }


def missing_domains(configs_dir: Path, domains: list[str]) -> list[str]:
    paths = ensure_zapret2_lists(configs_dir)
    existing = _list_entries(paths["hub"]) | _list_entries(paths["auto"])
    out: list[str] = []
    seen: set[str] = set()
    for item in domains:
        key = str(item or "").strip().lower().rstrip(".")
        if not key or key in seen or key in existing:
            continue
        seen.add(key)
        out.append(key)
    return out


def missing_ips(configs_dir: Path, ips: list[str]) -> list[str]:
    paths = ensure_zapret2_lists(configs_dir)
    existing = _list_entries(paths["ipset"])
    out: list[str] = []
    seen: set[str] = set()
    for item in ips:
        key = str(item or "").strip()
        if not key or key.lower() in seen or key.lower() in existing:
            continue
        seen.add(key.lower())
        out.append(key)
    return out


def hub_lists_initialized(configs_dir: Path, *, min_domains: int = 5) -> bool:
    paths = ensure_zapret2_lists(configs_dir)
    return len(_list_entries(paths["hub"])) >= min_domains


def write_hub_orchestrator_lua(path: Path, *, force: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    desired = _HUB_ORCHESTRATOR_LUA.lstrip("\n")
    if not force and path.exists():
        try:
            if path.read_text(encoding="utf-8") == desired:
                return path
        except Exception:
            pass
        # Keep existing file if user/orchestrator already wrote a compatible copy;
        # only refresh when missing markers for hub_tls.
        try:
            current = path.read_text(encoding="utf-8", errors="ignore")
            if "function hub_tls" in current and "function hub_discord" in current:
                return path
        except Exception:
            pass
    path.write_text(desired, encoding="utf-8")
    return path


def write_hub_targets_lua(path: Path, *, force: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not force and path.exists():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "HUB_TARGET_DOMAINS" in text and "HUB_TARGET_NETWORKS" in text:
                return path
        except Exception:
            pass
    domain_lines = ",\n    ".join(f'"{d}"' for d in BYPASS_SEED_DOMAINS)
    net_lines = ",\n    ".join(f'"{n}"' for n in BYPASS_SEED_NETWORKS)
    path.write_text(
        "-- Generated by Zapret Hub from bypass-youtube-discord.lua catalogs.\n"
        "-- Matching is done via hostlist/ipset files; this table is for Lua helpers/debug.\n"
        "HUB_TARGET_DOMAINS = {\n"
        f"    {domain_lines}\n"
        "}\n"
        "HUB_TARGET_NETWORKS = {\n"
        f"    {net_lines}\n"
        "}\n",
        encoding="utf-8",
    )
    return path


def write_hub_strategy_lua(configs_dir: Path, strategy_id: str) -> Path:
    sid = strategy_id if strategy_id in STRATEGY_IDS else "balanced"
    paths = ensure_zapret2_lists(configs_dir)
    path = paths["lua_strategy"]
    path.write_text(
        "-- Generated by Zapret Hub orchestrator. Do not edit by hand.\n"
        f'HUB_STRATEGY = "{sid}"\n',
        encoding="utf-8",
    )
    return path


def prepare_zapret2_runtime_files(configs_dir: Path, strategy_id: str) -> dict[str, Path]:
    paths = ensure_zapret2_lists(configs_dir)
    write_hub_orchestrator_lua(paths["lua_orch"])
    write_hub_targets_lua(paths["lua_targets"])
    write_hub_strategy_lua(configs_dir, strategy_id)
    return paths


def _append_unique(path: Path, lines: list[str]) -> list[str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[str] = []
    if path.exists():
        existing = [row.rstrip() for row in path.read_text(encoding="utf-8", errors="ignore").splitlines()]
    seen = {row.strip().lower() for row in existing if row.strip() and not row.lstrip().startswith("#")}
    added: list[str] = []
    for line in lines:
        key = line.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        existing.append(line.strip())
        added.append(line.strip())
    if added:
        path.write_text("\n".join(existing) + ("\n" if existing else ""), encoding="utf-8")
    return added


def add_domains(configs_dir: Path, domains: list[str]) -> list[str]:
    paths = ensure_zapret2_lists(configs_dir)
    cleaned = [d.strip().lower().rstrip(".") for d in domains if d and d.strip()]
    return _append_unique(paths["hub"], cleaned)


def add_ips(configs_dir: Path, ips: list[str]) -> list[str]:
    paths = ensure_zapret2_lists(configs_dir)
    cleaned = [item.strip() for item in ips if item and item.strip()]
    return _append_unique(paths["ipset"], cleaned)


def exclude_domains(configs_dir: Path, domains: list[str]) -> list[str]:
    paths = ensure_zapret2_lists(configs_dir)
    cleaned = [d.strip().lower().rstrip(".") for d in domains if d and d.strip()]
    return _append_unique(paths["exclude"], cleaned)


def seed_bypass_catalog(configs_dir: Path, *, only_missing: bool = True) -> dict[str, list[str]]:
    """Append bypass-youtube-discord.lua catalogs without wiping existing entries."""
    domains = list(BYPASS_SEED_DOMAINS)
    ips = list(BYPASS_SEED_NETWORKS)
    if only_missing:
        domains = missing_domains(configs_dir, domains)
        ips = missing_ips(configs_dir, ips)
    return {
        "domains": add_domains(configs_dir, domains) if domains else [],
        "ips": add_ips(configs_dir, ips) if ips else [],
    }


def seed_service_lists(
    configs_dir: Path, service_ids: list[str], *, only_missing: bool = True
) -> dict[str, list[str]]:
    domains = harvest_service_domains(service_ids)
    ips = harvest_service_ips(service_ids)
    if only_missing:
        domains = missing_domains(configs_dir, domains)
        ips = missing_ips(configs_dir, ips)
    return {
        "domains": add_domains(configs_dir, domains) if domains else [],
        "ips": add_ips(configs_dir, ips) if ips else [],
    }


def harvest_service_domains(service_ids: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    extras = list(BYPASS_SEED_DOMAINS) if any(s in {"youtube", "discord"} for s in service_ids) else []
    for service_id in service_ids:
        rule = SERVICE_RULES.get(service_id)
        items = list(rule.list_general or ()) + list(rule.list_google or ()) if rule else []
        for item in items:
            host = str(item).strip().lower().rstrip(".")
            if not host or host in seen:
                continue
            seen.add(host)
            out.append(host)
    for host in extras:
        key = host.strip().lower().rstrip(".")
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def harvest_service_ips(service_ids: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    extras = list(BYPASS_SEED_NETWORKS) if any(s in {"youtube", "discord"} for s in service_ids) else []
    for service_id in service_ids:
        rule = SERVICE_RULES.get(service_id)
        if rule is None:
            continue
        for item in rule.ipset_all or ():
            value = str(item).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            out.append(value)
    for value in extras:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def bundle_winws_root(winws2_path: Path) -> Path:
    return Path(winws2_path).resolve().parent


def _filter_file(bundle_root: Path, name: str) -> Path | None:
    candidate = bundle_root / "windivert.filter" / name
    return candidate if candidate.is_file() else None


def find_bundle_lua(bundle_root: Path, filename: str) -> Path | None:
    for candidate in (bundle_root / "lua" / filename, bundle_root / filename):
        if candidate.is_file():
            return candidate
    return None


def build_default_profile_args(
    *,
    lists: dict[str, Path],
    bundle_root: Path,
    tcp_ports: str,
    strategy_id: str = "balanced",
) -> list[str]:
    """Filter/desync profiles; lua-init files must already be on the command line."""
    _ = strategy_id
    hub = str(lists["hub"])
    auto = str(lists["auto"])
    exclude = str(lists["exclude"])
    ipset = str(lists["ipset"])
    hostlist_args = [
        f"--hostlist={hub}",
        f"--hostlist-auto={auto}",
        f"--hostlist-exclude={exclude}",
        f"--ipset={ipset}",
    ]
    auto_args = [
        "--hostlist-auto-fail-threshold=2",
        "--hostlist-auto-fail-time=60",
    ]

    args: list[str] = []
    for name in (
        "windivert_part.discord_media.txt",
        "windivert_part.stun.txt",
        "windivert_part.quic_initial_ietf.txt",
    ):
        path = _filter_file(bundle_root, name)
        if path is not None:
            args.append(f"--wf-raw-part=@{path}")

    args.extend(
        [
            "--filter-tcp=80",
            "--filter-l7=http",
            *hostlist_args,
            *auto_args,
            "--payload=http_req",
            "--lua-desync=hub_http",
            "--lua-desync=hub_http_b",
            "--new",
            f"--filter-tcp={tcp_ports}",
            "--filter-l7=tls",
            *hostlist_args,
            *auto_args,
            "--payload=tls_client_hello",
            "--lua-desync=hub_tls",
            "--lua-desync=hub_tls_b",
            "--new",
            "--filter-udp=443",
            "--filter-l7=quic",
            *hostlist_args,
            *auto_args,
            "--payload=quic_initial",
            "--lua-desync=hub_quic",
            "--new",
            "--filter-l7=wireguard,stun,discord",
            "--payload=wireguard_initiation,wireguard_cookie,stun,discord_ip_discovery",
            "--lua-desync=hub_discord",
        ]
    )
    return args


def next_strategy_id(current: str) -> str:
    current = (current or "balanced").strip() or "balanced"
    if current not in STRATEGY_IDS:
        return STRATEGY_IDS[0]
    idx = STRATEGY_IDS.index(current)
    return STRATEGY_IDS[(idx + 1) % len(STRATEGY_IDS)]


def describe_strategy(strategy_id: str, *, language: str = "ru") -> str:
    labels = {
        "balanced": ("Сбалансированная Lua", "Balanced Lua"),
        "fake_heavy": ("Агрессивный fake", "Aggressive fake"),
        "multisplit": ("Multisplit Lua", "Multisplit Lua"),
    }
    ru, en = labels.get(strategy_id, (strategy_id, strategy_id))
    return ru if str(language).startswith("ru") else en


def strategy_generals() -> list[dict[str, str]]:
    return [
        {"id": sid, "bundle_id": "zapret2", "name": describe_strategy(sid, language="en")}
        for sid in STRATEGY_IDS
    ]


_MOD_OVERLAY_START = "# --- zapret-hub-mod-overlays ---"
_MOD_OVERLAY_END = "# --- end zapret-hub-mod-overlays ---"


def _strip_mod_overlay(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    skipping = False
    for line in lines:
        stripped = line.strip()
        if stripped == _MOD_OVERLAY_START:
            skipping = True
            continue
        if stripped == _MOD_OVERLAY_END:
            skipping = False
            continue
        if not skipping:
            out.append(line)
    return "\n".join(out).rstrip() + ("\n" if out else "")


def _collect_mod_list_lines(mod_root: Path) -> tuple[list[str], list[str], list[str]]:
    """Return (domains, excludes, ips) from a Zapret2 mod folder."""
    domains: list[str] = []
    excludes: list[str] = []
    ips: list[str] = []
    lists_dir = mod_root / "lists"
    roots = [lists_dir] if lists_dir.is_dir() else []
    roots.append(mod_root)
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.txt")):
            name = path.name.lower()
            try:
                rows = [
                    row.strip()
                    for row in path.read_text(encoding="utf-8", errors="ignore").splitlines()
                    if row.strip() and not row.lstrip().startswith("#")
                ]
            except Exception:
                continue
            if "exclude" in name:
                excludes.extend(rows)
            elif "ipset" in name or name.startswith("ip"):
                ips.extend(rows)
            else:
                domains.extend(rows)
    return domains, excludes, ips


def merge_mod_overlays(configs_dir: Path, mod_roots: list[Path]) -> dict[str, object]:
    """Merge enabled Zapret2 mod lists/lua into Hub configs/zapret2 (separate from classic)."""
    paths = ensure_zapret2_lists(configs_dir)
    all_domains: list[str] = []
    all_excludes: list[str] = []
    all_ips: list[str] = []
    seen_d: set[str] = set()
    seen_e: set[str] = set()
    seen_i: set[str] = set()
    lua_copied: list[str] = []

    mod_lua_root = paths["hub"].parent / "mod_lua"
    if mod_lua_root.exists():
        shutil.rmtree(mod_lua_root, ignore_errors=True)
    mod_lua_root.mkdir(parents=True, exist_ok=True)

    for mod_root in mod_roots:
        root = Path(mod_root)
        if not root.is_dir():
            continue
        domains, excludes, ips = _collect_mod_list_lines(root)
        for item in domains:
            key = item.lower()
            if key in seen_d:
                continue
            seen_d.add(key)
            all_domains.append(item)
        for item in excludes:
            key = item.lower()
            if key in seen_e:
                continue
            seen_e.add(key)
            all_excludes.append(item)
        for item in ips:
            key = item.lower()
            if key in seen_i:
                continue
            seen_i.add(key)
            all_ips.append(item)
        for lua in sorted(root.glob("*.lua")):
            target = mod_lua_root / f"{root.name}__{lua.name}"
            try:
                target.write_text(lua.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
                lua_copied.append(str(target.name))
            except Exception:
                continue

    def _rewrite(path: Path, overlay_lines: list[str]) -> None:
        base = ""
        if path.exists():
            try:
                base = _strip_mod_overlay(path.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                base = ""
        if not overlay_lines:
            path.write_text(base, encoding="utf-8")
            return
        block = "\n".join([_MOD_OVERLAY_START, *overlay_lines, _MOD_OVERLAY_END, ""])
        path.write_text((base.rstrip() + "\n\n" if base.strip() else "") + block, encoding="utf-8")

    _rewrite(paths["hub"], all_domains)
    _rewrite(paths["exclude"], all_excludes)
    _rewrite(paths["ipset"], all_ips)
    return {
        "domains": len(all_domains),
        "excludes": len(all_excludes),
        "ips": len(all_ips),
        "lua": lua_copied,
        "mods": len(mod_roots),
    }
