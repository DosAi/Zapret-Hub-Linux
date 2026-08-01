from pathlib import Path


QUICK_ACCESS = Path(__file__).parents[1] / "web_ui" / "src" / "pages" / "QuickAccessPage.tsx"


def test_runtime_wheel_browses_without_backend_commit() -> None:
    source = QUICK_ACCESS.read_text(encoding="utf-8")
    wheel_handler = source.split("const onWheel = (event: WheelEvent) => {", 1)[1].split(
        "stage.addEventListener", 1
    )[0]

    assert "setPreviewMode" in wheel_handler
    assert "runtime.select" not in wheel_handler
    assert "scheduleModeCommit" not in source
    assert "MODE_SETTLE_MS" not in source


def test_power_button_commits_previewed_runtime() -> None:
    source = QUICK_ACCESS.read_text(encoding="utf-8")
    power_handler = source.split("const togglePower = () => {", 1)[1].split(
        "const runtimeLabel", 1
    )[0]

    assert 'bridge.call("runtime.select", { id: target, keepPower: true })' in power_handler
    assert 'bridge.call("runtime.power", { on: nextOn })' in power_handler


def test_quick_access_exposes_independent_tg_proxy_toggle() -> None:
    source = QUICK_ACCESS.read_text(encoding="utf-8")

    assert 'import { IosToggle }' in source
    assert 'bridge.call("component.toggle", { id: "tg-ws-proxy", on: enabled })' in source
    assert 'TG Proxy: включать вместе с обходом' in source
    assert 'event.stopPropagation()' in source
