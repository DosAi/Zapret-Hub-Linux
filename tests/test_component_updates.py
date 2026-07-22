from __future__ import annotations

from types import SimpleNamespace

from zapret_hub.services.components import ProcessManager


RELEASE_FEED = b'''<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Release 1.10.0</title>
    <link rel="alternate" href="https://github.com/Flowseal/zapret-discord-youtube/releases/tag/1.10.0"/>
  </entry>
</feed>'''

TG_RELEASE_FEED = b'''<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Release v1.8.1</title>
    <link rel="alternate" href="https://github.com/Flowseal/tg-ws-proxy/releases/tag/v1.8.1"/>
  </entry>
</feed>'''

COMMIT_FEED = b'''<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Update bundle</title>
    <link rel="alternate" href="https://github.com/bol-van/zapret-win-bundle/commit/f4cf5dde162ae35e6f3a2fd72dde3e86b57dc278"/>
  </entry>
</feed>'''


class FakeLogging:
    def log(self, *_args, **_kwargs) -> None:
        return None


class FeedGitHub:
    def github_json(self, *_args, **_kwargs):
        raise RuntimeError("HTTP Error 403: rate limit exceeded")

    def github_bytes(self, url: str, **_kwargs) -> bytes:
        if "tg-ws-proxy" in url:
            return TG_RELEASE_FEED
        if "commits/master.atom" in url:
            return COMMIT_FEED
        return RELEASE_FEED


def manager() -> ProcessManager:
    process = ProcessManager.__new__(ProcessManager)
    process.github = FeedGitHub()
    process.logging = FakeLogging()
    return process


def test_zapret_release_falls_back_to_atom_after_rate_limit() -> None:
    release = manager().fetch_latest_zapret_release()
    assert release["latest_version"] == "1.10.0"
    assert release["asset_url"].endswith("/1.10.0/zapret-discord-youtube-1.10.0.zip")
    assert release["zipball_url"].endswith("/refs/tags/1.10.0")


def test_tg_proxy_release_falls_back_to_atom_after_rate_limit() -> None:
    release = manager().fetch_latest_tg_ws_proxy_release()
    assert release["latest_version"] == "1.8.1"
    assert release["source_url"].endswith("/refs/tags/v1.8.1")
    assert release["exe_url"].endswith("/v1.8.1/TgWsProxy_windows.exe")


def test_zapret2_release_is_pinned_to_latest_bundle_commit() -> None:
    release = manager().fetch_latest_zapret2_release()
    assert release["latest_version"] == "f4cf5dde162a"
    assert release["source_url"].endswith("/zip/f4cf5dde162ae35e6f3a2fd72dde3e86b57dc278")


def test_zapret2_auto_discord_capture_includes_voice_udp_ranges() -> None:
    process = ProcessManager.__new__(ProcessManager)
    process.settings = SimpleNamespace(
        get=lambda: SimpleNamespace(
            zapret2_tcp_ports="80,443",
            zapret2_udp_ports="443",
            selected_service_ids=["discord"],
            zapret_control_mode="auto",
        )
    )
    udp_ports = process._normalize_zapret2_ports("443", "443")
    udp_ports = process._merge_zapret2_ports(udp_ports, "3478-3497,19294-19344,42377-62133")
    assert udp_ports == "443,3478-3497,19294-19344,42377-62133"
