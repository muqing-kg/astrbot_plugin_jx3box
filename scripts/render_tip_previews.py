# -*- coding: utf-8 -*-
"""Render local item-tip HTML samples to transparent PNG previews."""
from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "data" / "samples" / "tip_preview_schema"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="Directory containing item-tip HTML files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="PNG output directory (default: <source>/png).",
    )
    parser.add_argument("--scale", type=float, default=2, help="Device scale factor.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    output = (args.output or source / "png").resolve()
    html_files = sorted(source.glob("*.html"))
    if not html_files:
        raise SystemExit(f"No HTML previews found in {source}")

    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(
            viewport={"width": 500, "height": 900},
            device_scale_factor=args.scale,
        )
        try:
            for html_path in html_files:
                page.goto(html_path.as_uri(), wait_until="networkidle", timeout=60_000)
                page.wait_for_timeout(800)
                target = page.locator("#tip-root")
                png_path = output / f"{html_path.stem}.png"
                if target.count():
                    target.first.screenshot(path=str(png_path), omit_background=True)
                else:
                    page.screenshot(path=str(png_path), omit_background=True)
                print(f"wrote {png_path} ({png_path.stat().st_size} bytes)")
        finally:
            browser.close()

    print(f"rendered {len(html_files)} preview(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
