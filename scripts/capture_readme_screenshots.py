#!/usr/bin/env python3
"""Capture credential-free README screenshots from the Web UI mock preview."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url", help="Vite development URL, for example http://127.0.0.1:5173")
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    browser = shutil.which("chromium") or shutil.which("chromium-browser")
    if not browser:
        raise SystemExit("Chromium is required to capture README screenshots")
    captures = [
        ("main.png", "/?theme=night"),
        ("components.png", "/?theme=night&previewPage=components"),
        ("services.png", "/?theme=night&onboardingStep=2"),
    ]
    with tempfile.TemporaryDirectory(prefix="zapret-hub-screenshots-") as profile:
        for name, suffix in captures:
            output = (args.output_dir / name).resolve()
            subprocess.run(
                [
                    browser,
                    "--headless=new",
                    "--disable-gpu",
                    "--hide-scrollbars",
                    "--no-first-run",
                    "--no-default-browser-check",
                    f"--user-data-dir={profile}",
                    "--window-size=1080,550",
                    "--force-device-scale-factor=1",
                    "--run-all-compositor-stages-before-draw",
                    "--virtual-time-budget=5000",
                    f"--screenshot={output}",
                    args.base_url.rstrip("/") + suffix,
                ],
                check=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
