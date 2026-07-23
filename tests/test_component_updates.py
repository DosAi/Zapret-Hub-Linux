from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

from zapret_hub.services.components import ProcessManager
from zapret_hub.services.orchestrator.engine import OrchestratorEngine
from zapret_hub.ui.web_window import WebBridge


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


def test_zapret_release_is_pinned_to_1_9_9c() -> None:
    release = manager().fetch_latest_zapret_release()
    assert release["latest_version"] == "1.9.9c"
    assert release["asset_url"].endswith("/1.9.9c/zapret-discord-youtube-1.9.9c.zip")
    assert release["zipball_url"].endswith("/refs/tags/1.9.9c")
    assert release.get("pinned") == "1"


def test_tg_proxy_release_falls_back_to_atom_after_rate_limit() -> None:
    release = manager().fetch_latest_tg_ws_proxy_release()
    assert release["latest_version"] == "1.8.1"
    assert release["source_url"].endswith("/refs/tags/v1.8.1")
    assert release["exe_url"].endswith("/v1.8.1/TgWsProxy_windows.exe")


def test_zapret2_release_uses_bol_van_zapret2_tags() -> None:
    process = manager()

    class Zapret2GitHub(FeedGitHub):
        def github_json(self, url: str, **_kwargs):
            if "bol-van/zapret2/releases" in url:
                return [
                    {
                        "tag_name": "v1.0.3",
                        "draft": False,
                        "prerelease": False,
                        "published_at": "2026-07-20T12:00:00Z",
                        "zipball_url": "https://codeload.github.com/bol-van/zapret2/zip/refs/tags/v1.0.3",
                        "assets": [
                            {
                                "name": "zapret2-v1.0.3.zip",
                                "browser_download_url": "https://github.com/bol-van/zapret2/releases/download/v1.0.3/zapret2-v1.0.3.zip",
                            }
                        ],
                    }
                ]
            raise RuntimeError("HTTP Error 403: rate limit exceeded")

    process.github = Zapret2GitHub()
    release = process.fetch_latest_zapret2_release()
    assert release["latest_version"] == "1.0.3"
    assert "bol-van/zapret2" in release["source_url"]
    assert release["source_url"].endswith("zapret2-v1.0.3.zip")


def test_zapret2_auto_discord_capture_includes_voice_udp_ranges() -> None:
    process = ProcessManager.__new__(ProcessManager)
    process.settings = SimpleNamespace(
        get=lambda: SimpleNamespace(
            zapret2_tcp_ports="80,443",
            zapret2_udp_ports="443",
            selected_service_ids=["discord"],
            zapret2_control_mode="auto",
        )
    )
    udp_ports = process._normalize_zapret2_ports("443", "443")
    udp_ports = process._merge_zapret2_ports(udp_ports, "3478-3497,19294-19344,42377-62133")
    assert udp_ports == "443,3478-3497,19294-19344,42377-62133"
    tcp_ports = process._normalize_zapret2_ports("80,443", "80,443")
    tcp_ports = process._merge_zapret2_ports(tcp_ports, "2053,2083,2087,2096,8443")
    assert "2053" in tcp_ports
    assert "8443" in tcp_ports


def test_zapret_bundles_keep_installed_layer_order(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    base = tmp_path / "runtime" / "zapret-discord-youtube"
    for folder in (first, second, base):
        folder.mkdir(parents=True)

    installed = [
        {"id": "market", "path": str(first), "source_type": "zapret_bundle", "enabled": True, "marketplace_slug": "market"},
        {"id": "custom", "path": str(second), "source_type": "zapret_bundle", "enabled": True},
    ]

    class Storage:
        paths = SimpleNamespace(
            runtime_dir=tmp_path / "runtime",
            mods_dir=tmp_path / "mods",
            cache_dir=tmp_path / "cache",
            data_dir=tmp_path / "data",
        )

        @staticmethod
        def read_json(path: Path, default=None):
            return installed if path.name == "installed_mods.json" else default

    process = ProcessManager.__new__(ProcessManager)
    process.storage = Storage()

    assert [item["id"] for item in process._get_zapret_bundles(enabled_only=True)] == ["market", "custom", "base"]


def test_marketplace_bundle_overlays_complete_zapret_runtime(tmp_path: Path) -> None:
    base = tmp_path / "runtime" / "zapret-discord-youtube"
    mod = tmp_path / "mod"
    active = tmp_path / "active"
    for root in (base, mod):
        (root / "bin").mkdir(parents=True)
        (root / "lists").mkdir()
    (base / "general.bat").write_text("base", encoding="utf-8")
    (base / "bin" / "base.bin").write_bytes(b"base")
    (base / "lists" / "list-general.txt").write_text("base.example\n", encoding="utf-8")
    (mod / "market-general.bat").write_text("market", encoding="utf-8")
    (mod / "bin" / "market.bin").write_bytes(b"market")
    (mod / "lists" / "list-general.txt").write_text("market.example\n", encoding="utf-8")

    process = ProcessManager.__new__(ProcessManager)
    process.storage = SimpleNamespace(paths=SimpleNamespace(runtime_dir=tmp_path / "runtime"))
    process._next_active_runtime_dir = lambda: active
    process._get_zapret_bundles = lambda enabled_only: [
        {"id": "market", "path": mod, "marketplace": True},
        {"id": "base", "path": base, "marketplace": False},
    ]
    process._apply_selected_service_rules = lambda *_args, **_kwargs: None
    process._apply_user_collection_overrides = lambda *_args, **_kwargs: None
    process._apply_gaming_set_list_overlays = lambda *_args, **_kwargs: None
    process._materialize_visible_merged_runtime = lambda *_args, **_kwargs: None

    result = process._materialize_zapret_runtime(
        selected_bundle_root=base,
        selected_bundle_id="base",
        selected_script_name="general.bat",
    )

    assert (result / "market-general.bat").read_text(encoding="utf-8") == "market"
    assert (result / "bin" / "market.bin").read_bytes() == b"market"
    assert not (result / "bin" / "base.bin").exists()


def test_service_change_restarts_running_zapret() -> None:
    events: list[str] = []
    values = SimpleNamespace(
        selected_service_ids=[],
        enabled_component_ids=["zapret"],
        autostart_component_ids=[],
        zapret_control_mode="manual",
    )

    class Settings:
        @staticmethod
        def get():
            return values

        @staticmethod
        def update(**changes):
            for key, value in changes.items():
                setattr(values, key, value)

    class Processes:
        running = {"zapret"}

        @classmethod
        def list_states(cls):
            return [SimpleNamespace(component_id=item, status="running") for item in cls.running]

        @classmethod
        def stop_component(cls, component_id: str):
            events.append(f"stop:{component_id}")
            cls.running.discard(component_id)

        @classmethod
        def start_component(cls, component_id: str):
            events.append(f"start:{component_id}")
            cls.running.add(component_id)
            return SimpleNamespace(status="running", component_id=component_id)

        @classmethod
        def seamless_restart_zapret(cls):
            events.append("seamless:zapret")
            cls.running.add("zapret")
            return SimpleNamespace(status="running", component_id="zapret")

    bridge = WebBridge.__new__(WebBridge)
    bridge.context = SimpleNamespace(
        settings=Settings(),
        processes=Processes(),
        merge=SimpleNamespace(rebuild=lambda: events.append("rebuild")),
        files=SimpleNamespace(
            _invalidate_collection_cache=lambda: None,
            rebuild_materialized_collections=lambda: events.append("collections"),
        ),
        logging=FakeLogging(),
    )
    bridge._runtime_reconfigure_lock = threading.Lock()
    bridge._runtime_transition_status = "on"
    bridge._service_power_hold = 0
    bridge.emit_state = lambda *args, **kwargs: None
    bridge._hold_service_power = lambda: 1
    bridge._release_service_power = lambda *_a, **_k: None
    bridge._emit_runtime_status = lambda *_a, **_k: None
    bridge._set_auxiliary_components_power_async = lambda *_a, **_k: None
    bridge._sync_orchestrator_lifecycle = lambda: None
    bridge._component_running = lambda cid: cid in Processes.running

    bridge._apply_selected_services(["youtube", "discord"], emit=False)

    assert values.selected_service_ids == ["discord", "youtube"]
    assert "zapret" in values.enabled_component_ids
    assert events == ["rebuild", "collections", "seamless:zapret"]


def test_clearing_bypass_services_stops_zapret_without_restart() -> None:
    events: list[str] = []
    values = SimpleNamespace(
        selected_service_ids=["youtube"],
        enabled_component_ids=["zapret"],
        autostart_component_ids=["zapret"],
        selected_runtime_mode="zapret",
        zapret_control_mode="manual",
    )

    class Settings:
        @staticmethod
        def get():
            return values

        @staticmethod
        def update(**changes):
            for key, value in changes.items():
                setattr(values, key, value)

    class Processes:
        running = {"zapret"}

        @classmethod
        def list_states(cls):
            return [SimpleNamespace(component_id=item, status="running") for item in cls.running]

        @classmethod
        def stop_component(cls, component_id: str):
            events.append(f"stop:{component_id}")
            cls.running.discard(component_id)

        @classmethod
        def start_component(cls, component_id: str):
            events.append(f"start:{component_id}")

    bridge = WebBridge.__new__(WebBridge)
    bridge.context = SimpleNamespace(
        settings=Settings(),
        processes=Processes(),
        merge=SimpleNamespace(rebuild=lambda: events.append("rebuild")),
        files=SimpleNamespace(
            _invalidate_collection_cache=lambda: None,
            rebuild_materialized_collections=lambda: None,
        ),
        logging=FakeLogging(),
    )
    bridge._runtime_reconfigure_lock = threading.Lock()
    bridge._runtime_transition_status = "on"
    bridge._service_power_hold = 0
    bridge.emit_state = lambda *args, **kwargs: None
    bridge._hold_service_power = lambda: 1
    bridge._release_service_power = lambda *_a, **_k: None
    bridge._emit_runtime_status = lambda *_a, **_k: None
    bridge._set_auxiliary_components_power_async = lambda *_a, **_k: None
    bridge._sync_orchestrator_lifecycle = lambda: None
    bridge._component_running = lambda cid: cid in Processes.running

    bridge._apply_selected_services([], emit=False)

    assert "zapret" not in values.enabled_component_ids
    assert "zapret" not in values.autostart_component_ids
    assert events == ["stop:zapret", "rebuild"]


def test_auto_resume_restarts_zapret_with_rebuilt_services(tmp_path: Path) -> None:
    events: list[str] = []
    values = SimpleNamespace(
        selected_runtime_mode="zapret",
        selected_service_ids=["youtube"],
        enabled_component_ids=["zapret"],
        trusted_general="base|general.bat",
        zapret_control_mode="auto",
        general_autotest_done=True,
    )

    class Settings:
        @staticmethod
        def get():
            return values

        @staticmethod
        def update(**changes):
            for key, value in changes.items():
                setattr(values, key, value)

    class Processes:
        @staticmethod
        def list_states():
            return [SimpleNamespace(component_id="zapret", status="running")]

        @staticmethod
        def stop_component(component_id: str):
            events.append(f"stop:{component_id}")

        @staticmethod
        def start_component(component_id: str):
            events.append(f"start:{component_id}")

        @staticmethod
        def rebuild_zapret_runtime_snapshot():
            events.append("snapshot")

    configs = tmp_path / "configs"
    configs.mkdir()
    engine = OrchestratorEngine()
    engine.context = SimpleNamespace(
        settings=Settings(),
        processes=Processes(),
        merge=SimpleNamespace(rebuild=lambda: events.append("rebuild")),
        files=SimpleNamespace(
            _invalidate_collection_cache=lambda: None,
            rebuild_materialized_collections=lambda: events.append("collections"),
        ),
        paths=SimpleNamespace(configs_dir=configs),
        knowledge=None,
        logging=FakeLogging(),
    )
    engine._cutover = SimpleNamespace(snapshot=lambda: events.append("cutover"))
    engine.sync_lifecycle = lambda **_kwargs: {}

    result = engine.run_bootstrap(youtube=True, discord=True)

    assert result["ok"] is True
    assert result["resumed"] is True
    assert values.selected_service_ids == ["discord", "youtube"]
    assert events[-3:] == ["stop:zapret", "start:zapret", "cutover"]
