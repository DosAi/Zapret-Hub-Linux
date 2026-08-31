from __future__ import annotations

from pathlib import Path
import tempfile

from zapret_hub.services.browser_config import (
    MARKER_START,
    MARKER_END,
    configure_gecko_profile,
    discover_gecko_profiles,
    setup_all_gecko_browsers,
)


def test_discover_gecko_profiles_finds_directories_with_prefs_js() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        profile1 = root / "zen" / "profile1.default"
        profile1.mkdir(parents=True)
        (profile1 / "prefs.js").write_text("user_pref('test', 1);", encoding="utf-8")

        profile2 = root / "firefox" / "profile2.default"
        profile2.mkdir(parents=True)
        (profile2 / "prefs.js").write_text("user_pref('test', 2);", encoding="utf-8")

        empty_dir = root / "zen" / "empty"
        empty_dir.mkdir(parents=True)

        found = discover_gecko_profiles(roots=[root / "zen", root / "firefox"])

        assert len(found) == 2
        assert profile1 in found
        assert profile2 in found
        assert empty_dir not in found


def test_configure_gecko_profile_injects_zapret_block() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        profile_dir = Path(temp_dir)
        user_js = profile_dir / "user.js"
        user_js.write_text("user_pref('custom.setting', true);\n", encoding="utf-8")

        result = configure_gecko_profile(profile_dir)

        assert result == user_js
        content = user_js.read_text(encoding="utf-8")
        assert "user_pref('custom.setting', true);" in content
        assert MARKER_START in content
        assert MARKER_END in content
        assert 'user_pref("network.trr.mode", 2);' in content
        assert 'user_pref("network.trr.uri", "https://cloudflare-dns.com/dns-query");' in content
        assert 'user_pref("network.trr.bootstrapAddress", "1.1.1.1");' in content
        assert 'user_pref("network.http.http3.enable", false);' in content


def test_configure_gecko_profile_revert_removes_block() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        profile_dir = Path(temp_dir)
        user_js = profile_dir / "user.js"
        user_js.write_text("user_pref('custom.setting', true);\n", encoding="utf-8")

        configure_gecko_profile(profile_dir)
        assert MARKER_START in user_js.read_text(encoding="utf-8")

        configure_gecko_profile(profile_dir, revert=True)
        content = user_js.read_text(encoding="utf-8")
        assert MARKER_START not in content
        assert MARKER_END not in content
        assert "user_pref('custom.setting', true);" in content


def test_setup_all_gecko_browsers_processes_all_profiles() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        profile = root / "zen" / "abc.default"
        profile.mkdir(parents=True)
        (profile / "prefs.js").write_text("", encoding="utf-8")

        modified = setup_all_gecko_browsers(roots=[root / "zen"])
        assert len(modified) == 1
        assert (profile / "user.js").is_file()
