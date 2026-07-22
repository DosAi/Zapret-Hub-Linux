from zapret_hub.services.marketplace import MarketplaceService


def test_version_compare():
    svc = MarketplaceService.__new__(MarketplaceService)
    assert svc._is_newer("1.2.0", "1.1.9")
    assert svc._is_newer("2.0.0", "1.9.9")
    assert not svc._is_newer("1.0.0", "1.0.0")
    assert not svc._is_newer("1.0.0", "1.0.1")


def test_dismiss_until_newer(tmp_path):
    class Paths:
        data_dir = tmp_path
        cache_dir = tmp_path / "cache"

    class Logging:
        def log(self, *a, **k):
            pass

    svc = MarketplaceService(storage_paths=Paths(), logging=Logging(), mods=None, mods2=None)
    svc._update_cache = {
        "youtube-flow": {"slug": "youtube-flow", "latestVersion": "1.1.0", "title": "YT"},
    }
    svc.dismiss_updates([{"slug": "youtube-flow", "latestVersion": "1.1.0"}])
    assert svc._dismissals["youtube-flow"] == "1.1.0"

    # Same latest should not notify.
    svc._update_cache = {
        "youtube-flow": {
            "slug": "youtube-flow",
            "latestVersion": "1.1.0",
            "currentVersion": "1.0.0",
            "title": "YT",
        }
    }
    # Simulate notify filter
    notify = []
    for row in svc._update_cache.values():
        dismissed = svc._dismissals.get(row["slug"], "")
        if not dismissed or svc._is_newer(row["latestVersion"], dismissed):
            notify.append(row)
    assert notify == []

    # Newer release should notify again.
    row = {
        "slug": "youtube-flow",
        "latestVersion": "1.2.0",
        "currentVersion": "1.0.0",
        "title": "YT",
    }
    dismissed = svc._dismissals.get(row["slug"], "")
    assert svc._is_newer(row["latestVersion"], dismissed)
