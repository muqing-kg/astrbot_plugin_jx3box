"""Offline smoke checks (no AstrBot / t2i required).

Production tip/quest images are produced by Star.html_render -> astrbot-t2i.
This script only validates:
- help image (PIL)
- tip/quest HTML template data generation
- API search when network is available
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_jx3box.render.html_util import sanitize_css_color
from astrbot_plugin_jx3box.api.http_client import HttpClient
from astrbot_plugin_jx3box.api.jx3_api import Jx3Api
from astrbot_plugin_jx3box.render.renderers import render_help_image
from astrbot_plugin_jx3box.render.tip_html import build_tip_html, build_tip_template_data
from astrbot_plugin_jx3box.render.quest_html import build_quest_html


async def main() -> None:
    out = ROOT / "data" / "cards"
    out.mkdir(parents=True, exist_ok=True)

    # local pure checks
    assert sanitize_css_color("red;}") == "#FFFFFF"
    assert sanitize_css_color("#00D24B") == "#00D24B"
    assert sanitize_css_color("rgb(0, 200, 72)") == "rgb(0, 200, 72)"

    help_path = render_help_image(out / "help.png")
    print("help:", help_path, os.path.getsize(help_path))

    sample_item = {
        "Name": "冒烟测试物品",
        "Quality": 5,
        "Desc": 'text="一段说明" font=100',
        "Level": 110,
        "GetType": "活动",
    }
    kind, html = build_tip_html(sample_item)
    tip_html_path = out / "item_demo.html"
    tip_html_path.write_text(html, encoding="utf-8")
    data = build_tip_template_data(sample_item)
    assert data["rows"], "tip rows empty"
    assert all(str(r.get("color", "")).startswith("#") or str(r.get("color", "")).startswith("rgb") for r in data["rows"] if r.get("color"))
    print("item tip html:", tip_html_path, "kind=", kind, "rows=", len(data["rows"]))

    sample_quest = {
        "id": 31416,
        "name": "茶馆问讯",
        "desc": {"Objective": "text=\"打听消息\" font=100", "Description": "text=\"去茶馆\" font=100"},
        "start": {"mapName": "扬州", "name": "茶博士"},
        "end": {"mapName": "扬州", "name": "茶博士"},
        "rewards": [],
    }
    qhtml = await build_quest_html(sample_quest)
    quest_html_path = out / "quest_demo.html"
    quest_html_path.write_text(qhtml, encoding="utf-8")
    print("quest html:", quest_html_path, "bytes=", len(qhtml.encode("utf-8")))

    http = HttpClient(timeout=25, retries=1)
    api = Jx3Api(http, client="std")
    try:
        items = await api.search_items("龙木强弓")
        print("items:", [x.get("Name") for x in items[:5]])
        if items:
            try:
                detail = await api.get_item(items[0]["id"])
                print("item detail keys:", list(detail.keys())[:8] if detail else [])
            except Exception as e:
                print("item detail network skip:", type(e).__name__)
        quests = await api.search_quests("茶馆问讯")
        print("quests:", [x.get("name") for x in quests[:5]])
        if quests:
            try:
                qdetail = await api.get_quest(quests[0].get("id") or 31416)
                print("quest detail name:", (qdetail or {}).get("name"))
            except Exception as e:
                print("quest detail network skip:", type(e).__name__)
        achs = await api.search_achievements("武神重临")
        print("achs:", [(x.get("ID"), x.get("Name")) for x in achs[:5]])
        print("SMOKE_OK offline_html_path_note=production_uses_html_render_t2i")
    finally:
        await http.close()


if __name__ == "__main__":
    asyncio.run(main())
