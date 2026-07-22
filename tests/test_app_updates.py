from __future__ import annotations

from datetime import datetime, timezone

from zapret_hub.services.updates import UpdatesManager


MIRROR_FIXTURE = {
    "product": "Zapret Hub",
    "version": "2.1.2",
    "tag": "v2.1.2",
    "changelog": "• Fix one\n• Fix two",
    "github_url": "https://github.com/goshkow/Zapret-Hub/releases/tag/v2.1.2",
    "published_at": "2026-06-01T12:00:00Z",
    "binary_updated_at": "2026-06-01T12:30:00Z",
    "assets": {
        "installer": {
            "name": "Zapret_Hub_Setup_2.1.2.exe",
            "download_url": "https://goshkow.ru/zapret-hub/installer",
            "digest": "sha256:aaa",
            "size": 10,
        },
        "x64": {
            "name": "zapret_hub_2.1.2_portable_win_x64.zip",
            "download_url": "https://goshkow.ru/zapret-hub/x64",
            "digest": "sha256:bbb",
            "size": 20,
            "updated_at": "2026-06-01T12:30:00Z",
        },
        "arm64": {
            "name": "zapret_hub_2.1.2_portable_win_arm64.zip",
            "download_url": "https://goshkow.ru/zapret-hub/arm64",
            "digest": "sha256:ccc",
            "size": 21,
        },
    },
}


def test_normalize_mirror_payload_maps_download_urls() -> None:
    mgr = UpdatesManager.__new__(UpdatesManager)
    entries = UpdatesManager._normalize_release_entries(mgr, MIRROR_FIXTURE)
    assert len(entries) == 1
    assert entries[0]["version"] == "2.1.2"
    assert "Fix one" in str(entries[0]["body"])
    assets = entries[0]["payload"]["assets"]  # type: ignore[index]
    assert isinstance(assets, list)
    by_arch = {str(item.get("architecture")): item for item in assets}
    assert by_arch["x64"]["browser_download_url"] == "https://goshkow.ru/zapret-hub/x64"
    assert by_arch["arm64"]["browser_download_url"] == "https://goshkow.ru/zapret-hub/arm64"


def test_pick_release_asset_prefers_architecture_key(monkeypatch) -> None:
    mgr = UpdatesManager.__new__(UpdatesManager)
    entries = UpdatesManager._normalize_release_entries(mgr, MIRROR_FIXTURE)
    assets = entries[0]["payload"]["assets"]  # type: ignore[index]
    monkeypatch.setattr("zapret_hub.services.updates.platform.machine", lambda: "AMD64")
    picked = UpdatesManager._pick_release_asset(mgr, assets)  # type: ignore[arg-type]
    assert picked is not None
    assert picked["architecture"] == "x64"
    assert picked["browser_download_url"] == "https://goshkow.ru/zapret-hub/x64"


def test_pick_release_asset_arm(monkeypatch) -> None:
    mgr = UpdatesManager.__new__(UpdatesManager)
    entries = UpdatesManager._normalize_release_entries(mgr, MIRROR_FIXTURE)
    assets = entries[0]["payload"]["assets"]  # type: ignore[index]
    monkeypatch.setattr("zapret_hub.services.updates.platform.machine", lambda: "ARM64")
    picked = UpdatesManager._pick_release_asset(mgr, assets)  # type: ignore[arg-type]
    assert picked is not None
    assert picked["architecture"] == "arm64"


def test_version_compare_available_and_uptodate(monkeypatch) -> None:
    mgr = UpdatesManager.__new__(UpdatesManager)
    mgr.REPO_URL = UpdatesManager.REPO_URL
    monkeypatch.setattr("zapret_hub.services.updates.__version__", "2.0.0")
    monkeypatch.setattr(UpdatesManager, "_installed_build_timestamp", lambda self: None)
    status = UpdatesManager._build_application_release_status(mgr, MIRROR_FIXTURE)
    assert status["status"] == "available"
    assert status["latest_version"] == "2.1.2"
    assert status["asset_url"] == "https://goshkow.ru/zapret-hub/x64"
    assert status["asset_digest"].endswith("bbb") or "bbb" in status["asset_digest"]

    monkeypatch.setattr("zapret_hub.services.updates.__version__", "9.9.9")
    status2 = UpdatesManager._build_application_release_status(mgr, MIRROR_FIXTURE)
    assert status2["status"] == "up-to-date"


def test_same_version_hotfix_uses_archive_digest(monkeypatch) -> None:
    mgr = UpdatesManager.__new__(UpdatesManager)
    mgr.REPO_URL = UpdatesManager.REPO_URL
    monkeypatch.setattr("zapret_hub.services.updates.__version__", "2.1.2")
    monkeypatch.setattr(
        UpdatesManager,
        "_installed_build_timestamp",
        lambda self: datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(
        UpdatesManager,
        "_installed_release_identity",
        lambda self: {"version": "2.1.2", "digest": "old-digest"},
    )

    status = UpdatesManager._build_application_release_status(mgr, MIRROR_FIXTURE)

    assert status["status"] == "available"
    assert status["is_hotfix"] is True
    assert status["asset_digest"].endswith("bbb")


def test_same_version_same_digest_is_up_to_date(monkeypatch) -> None:
    mgr = UpdatesManager.__new__(UpdatesManager)
    mgr.REPO_URL = UpdatesManager.REPO_URL
    monkeypatch.setattr("zapret_hub.services.updates.__version__", "2.1.2")
    monkeypatch.setattr(
        UpdatesManager,
        "_installed_build_timestamp",
        lambda self: datetime(2026, 5, 1, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(
        UpdatesManager,
        "_installed_release_identity",
        lambda self: {"version": "2.1.2", "digest": "bbb"},
    )

    status = UpdatesManager._build_application_release_status(mgr, MIRROR_FIXTURE)

    assert status["status"] == "up-to-date"
    assert status["is_hotfix"] is False


def test_find_payload_exe_accepts_title_case(tmp_path) -> None:
    mgr = UpdatesManager.__new__(UpdatesManager)
    root = tmp_path / "payload"
    root.mkdir()
    (root / "Zapret_Hub.exe").write_bytes(b"mz")
    found = UpdatesManager._find_payload_exe(mgr, root)
    assert found is not None
    assert found.name.lower() == "zapret_hub.exe"
    assert UpdatesManager._resolve_payload_root(mgr, root) == root
