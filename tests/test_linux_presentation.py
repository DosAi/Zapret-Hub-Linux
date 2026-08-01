from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_linux_fork_branding_and_credits_are_present() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    locale = (PROJECT_ROOT / "web_ui/src/locale/dict.ts").read_text(encoding="utf-8")

    assert "Zapret Hub Linux" in readme
    assert "только на Kali Linux" in readme
    assert "Windows не поддерживается" in readme
    assert "https://github.com/DosAi/Zapret-Hub-Linux" in readme
    assert "https://t.me/dosai_main" in readme
    assert "ChatGPT" in readme
    assert "https://github.com/bol-van/zapret" in readme
    assert "https://github.com/bol-van/zapret2" in readme
    assert "https://github.com/Flowseal/tg-ws-proxy" in readme
    assert "shields.io" not in readme
    assert "stargazers" not in readme
    assert "goshkow.com" not in readme
    assert '"app.by": "by DosAi"' in locale


def test_linux_release_contains_a_real_png_window_icon() -> None:
    icon = PROJECT_ROOT / "ui_assets/icons/app.png"
    payload = icon.read_bytes()

    assert len(payload) > 1024
    assert payload.startswith(b"\x89PNG\r\n\x1a\n")


def test_happ_replaces_legacy_vpn_in_linux_navigation() -> None:
    components = (PROJECT_ROOT / "web_ui/src/pages/ComponentsPage.tsx").read_text(encoding="utf-8")
    onboarding = (PROJECT_ROOT / "web_ui/src/components/onboarding/OnboardingFlow.tsx").read_text(encoding="utf-8")
    settings = (PROJECT_ROOT / "web_ui/src/components/settings/SettingsModal.tsx").read_text(encoding="utf-8")

    order_line = next(line for line in components.splitlines() if line.startswith("const ORDER:"))
    assert "goshkow-vpn" in order_line
    assert "Happ" in components
    assert "Legacy VPN" not in components
    assert '["goshkow-vpn", "goshkow VPN"' not in onboarding
    assert '{ key: "vpn"' not in settings


def test_quick_cards_are_equal_and_window_has_room_for_statuses() -> None:
    quick_access = (PROJECT_ROOT / "web_ui/src/pages/QuickAccessPage.tsx").read_text(encoding="utf-8")
    window = (PROJECT_ROOT / "src/zapret_hub/ui/web_window.py").read_text(encoding="utf-8")

    assert "grid-cols-5" in quick_access
    assert "grid-cols-[1fr_1fr_1.22fr_1fr_1fr]" not in quick_access
    assert "_WINDOW_WIDTH = 940" in window
    assert "_WINDOW_HEIGHT = 550" in window


def test_github_automation_is_linux_only() -> None:
    ci = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "Linux CI" in ci
    assert "python-tests" in ci
    assert "frontend-build" in ci
    assert "windows-latest" not in ci
    assert not (PROJECT_ROOT / ".github/workflows/release.yml").exists()


def test_legacy_marketplace_is_not_exposed_or_contacted_on_linux() -> None:
    app = (PROJECT_ROOT / "web_ui/src/App.tsx").read_text(encoding="utf-8")
    sidebar = (PROJECT_ROOT / "web_ui/src/components/shell/Sidebar.tsx").read_text(encoding="utf-8")
    bridge = (PROJECT_ROOT / "src/zapret_hub/ui/web_window.py").read_text(encoding="utf-8")
    marketplace = (PROJECT_ROOT / "src/zapret_hub/services/marketplace.py").read_text(encoding="utf-8")
    updates = (PROJECT_ROOT / "src/zapret_hub/services/updates.py").read_text(encoding="utf-8")

    nav_line = next(line for line in app.splitlines() if line.startswith("const NAV_KEYS:"))
    assert '"marketplace"' not in nav_line
    assert '{ key: "marketplace"' not in sidebar
    assert 'href="https://github.com/DosAi/Zapret-Hub-Linux"' in sidebar
    assert 'if sys.platform.startswith("linux"):' in bridge
    assert "goshkow.com" not in marketplace
    assert "goshkow.com" not in updates
