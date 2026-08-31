from __future__ import annotations

import argparse
import json
from typing import Any

from zapret_hub.services.linux_zapret2 import LinuxZapret2Service, LinuxZapretService, result_dict


def _print_human(payload: dict[str, Any]) -> None:
    width = max(len(str(key)) for key in payload)
    for key, value in payload.items():
        if isinstance(value, list):
            value = " ".join(str(item) for item in value)
        print(f"{key:<{width}} : {value}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Zapret Hub Linux backend diagnostics and service control")
    parser.add_argument(
        "command",
        choices=("diagnose", "status", "start", "stop", "setup-browser"),
        nargs="?",
        default="diagnose",
    )
    parser.add_argument(
        "--backend",
        choices=("auto", "zapret", "zapret2"),
        default="auto",
        help="Linux service backend (default: detect an installed backend)",
    )
    parser.add_argument("--dry-run", action="store_true", help="show the privileged command without executing it")
    parser.add_argument("--revert", action="store_true", help="revert browser DoH configuration")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args(argv)

    if args.command == "setup-browser":
        from zapret_hub.services.browser_config import (
            discover_gecko_profiles,
            setup_all_gecko_browsers,
        )

        if args.dry_run:
            profiles = discover_gecko_profiles()
            payload = {
                "command": "setup-browser",
                "action": "preview",
                "profiles": [str(p / "user.js") for p in profiles],
            }
        else:
            modified = setup_all_gecko_browsers(revert=args.revert)
            action = "reverted" if args.revert else "configured"
            payload = {
                "command": "setup-browser",
                "action": action,
                "profiles": [str(p) for p in modified],
            }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            _print_human(payload)
        return 0

    classic_service = LinuxZapretService()
    if args.backend == "zapret":
        service = classic_service
        backend = "zapret"
    elif args.backend == "zapret2":
        service = LinuxZapret2Service()
        backend = "zapret2"
    elif classic_service.find_nfqws() is not None:
        service = classic_service
        backend = "zapret"
    else:
        service = LinuxZapret2Service()
        backend = "zapret2"
    if args.command == "diagnose":
        payload = service.diagnose()
    elif args.command == "status":
        payload = result_dict(service.status())
    else:
        operation = service.start if args.command == "start" else service.stop
        payload = result_dict(operation(dry_run=args.dry_run))
    payload = {"backend": backend, **payload}

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_human(payload)
    return 0 if payload.get("status") not in {"error", "unsupported"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
