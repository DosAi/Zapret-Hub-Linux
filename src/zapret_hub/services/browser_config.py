from __future__ import annotations

from pathlib import Path
import re
from typing import Sequence

MARKER_START = "// --- ZAPRET-HUB-CONFIG-START ---"
MARKER_END = "// --- ZAPRET-HUB-CONFIG-END ---"

ZAPRET_USER_JS_BLOCK = f"""{MARKER_START}
// Configured by Zapret Hub for direct DPI bypass in Russia
user_pref("network.proxy.type", 0);
user_pref("network.trr.mode", 2);
user_pref("network.trr.uri", "https://cloudflare-dns.com/dns-query");
user_pref("network.trr.custom_uri", "https://cloudflare-dns.com/dns-query");
user_pref("network.trr.default_provider_uri", "https://cloudflare-dns.com/dns-query");
user_pref("network.trr.bootstrapAddress", "1.1.1.1");
user_pref("network.dns.echconfig.enabled", true);
user_pref("network.dns.use_https_rr_as_alpn", true);
user_pref("network.http.http3.enable", false);
{MARKER_END}"""

_BLOCK_PATTERN = re.compile(
    re.escape(MARKER_START) + r"[\s\S]*?" + re.escape(MARKER_END) + r"\n?",
    re.MULTILINE,
)

DEFAULT_BROWSER_ROOTS = (
    Path.home() / ".config" / "zen",
    Path.home() / ".mozilla" / "firefox",
    Path.home() / ".librewolf",
    Path.home() / ".config" / "librewolf",
    Path.home() / ".floorp",
    Path.home() / ".config" / "floorp",
    Path.home() / ".waterfox",
)


def discover_gecko_profiles(roots: Sequence[Path] | None = None) -> list[Path]:
    """Find directories containing Gecko profile preferences (prefs.js)."""
    search_roots = roots if roots is not None else DEFAULT_BROWSER_ROOTS
    profiles: list[Path] = []
    for root in search_roots:
        if not root.is_dir():
            continue
        try:
            for prefs_file in root.glob("*/prefs.js"):
                if prefs_file.is_file():
                    profiles.append(prefs_file.parent.resolve())
        except OSError:
            continue
    return sorted(set(profiles))


def configure_gecko_profile(profile_dir: Path, *, revert: bool = False) -> Path:
    """Inject or remove the Zapret configuration block in user.js."""
    user_js = profile_dir / "user.js"
    current_content = ""
    if user_js.is_file():
        try:
            current_content = user_js.read_text(encoding="utf-8")
        except OSError:
            current_content = ""

    cleaned = _BLOCK_PATTERN.sub("", current_content).strip()

    if revert:
        if cleaned:
            user_js.write_text(cleaned + "\n", encoding="utf-8")
        elif user_js.exists():
            user_js.unlink(missing_ok=True)
        return user_js

    new_content = (cleaned + "\n\n" if cleaned else "") + ZAPRET_USER_JS_BLOCK + "\n"
    user_js.write_text(new_content, encoding="utf-8")
    return user_js


def setup_all_gecko_browsers(*, roots: Sequence[Path] | None = None, revert: bool = False) -> list[Path]:
    """Discover all browser profiles and configure user.js for each."""
    profiles = discover_gecko_profiles(roots)
    modified: list[Path] = []
    for profile in profiles:
        modified.append(configure_gecko_profile(profile, revert=revert))
    return modified
