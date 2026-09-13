# -*- coding: utf-8 -*-
"""Temp: build tip/quest HTML for the 8 reference samples and screenshot at 1x."""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_jx3box.api.http_client import HttpClient
from astrbot_plugin_jx3box.api.jx3_api import Jx3Api
from astrbot_plugin_jx3box.render.quest_html import build_quest_html, resolve_quest_item_meta
from astrbot_plugin_jx3box.render.tip_html import build_tip_html

OUT = ROOT / "data" / "samples" / "compare"
OUT.mkdir(parents=True, exist_ok=True)

QUESTS = (14267, 416, 14272)
ITEMS = ["香喷喷的烤肉|5_25746", "檀溪跃马|10_2149", "山间红日屏风|10_2013", "僵尸挂件1|8_19813"]


async def build_all() -> None:
    http = HttpClient(timeout=25)
    await http.start()
    api = Jx3Api(http, client="std")
    try:
        for qid in QUESTS:
            q = await api.get_quest(qid)
            meta = await resolve_quest_item_meta(api, q)
            html = await build_quest_html(q, item_meta=meta, api=api)
            (OUT / f"quest_{qid}.html").write_text(html, encoding="utf-8")
            print("quest", qid, "ok", len(html))
        import re

        for entry in ITEMS:
            name, _, iid = entry.partition("|")
            if iid:
                detail = await api.get_item(iid)
                if not detail:
                    print("miss", name)
                    continue
            else:
                rows = await api.search_items(name, per=20)
                row = next((r for r in rows if str(r.get("Name")) == name), rows[0] if rows else None)
                if not row:
                    print("miss", name)
                    continue
                detail = await api.get_item(row.get("id"))
                if not detail:
                    detail = row
            _, html = build_tip_html(detail)
            safe = re.sub(r"[《》·/\\]", "_", name)[:24]
            (OUT / f"tip_{safe}.html").write_text(html, encoding="utf-8")
            print("item", name, "q=", detail.get("Quality"))
    finally:
        await http.close()


asyncio.run(build_all())

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1200, "height": 900}, device_scale_factor=1)
    try:
        for f in sorted(OUT.glob("*.html")):
            page.goto(f.as_uri(), wait_until="networkidle", timeout=60_000)
            page.wait_for_timeout(600)
            sel = "#quest-root" if f.name.startswith("quest") else "#tip-root"
            loc = page.locator(sel)
            png = f.with_suffix(".png")
            if loc.count():
                loc.first.screenshot(path=str(png))
            else:
                page.screenshot(path=str(png))
            print("shot", png.name, png.stat().st_size)
    finally:
        browser.close()
print("COMPARE_BUILD_DONE")
