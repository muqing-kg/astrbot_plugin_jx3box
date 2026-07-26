"""local smoke test"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_jx3box.http_client import HttpClient
from astrbot_plugin_jx3box.jx3_api import Jx3Api
from astrbot_plugin_jx3box.renderers import render_help_image, render_item_tip, render_quest_card


async def main() -> None:
    out = ROOT / "data" / "cards"
    out.mkdir(parents=True, exist_ok=True)
    http = HttpClient(timeout=25)
    api = Jx3Api(http, client="std")
    try:
        help_path = render_help_image(out / "help.png")
        print("help:", help_path, os.path.getsize(help_path))
        items = await api.search_items("龙木强弓")
        print("items:", [x.get("Name") for x in items[:5]])
        if not items:
            raise SystemExit("item search empty")
        detail = await api.get_item(items[0]["id"])
        icon = await api.get_icon_bytes(detail.get("IconID") or items[0].get("IconID"))
        item_path = render_item_tip(detail or items[0], icon, out / "item_demo.png")
        print("item tip:", item_path, os.path.getsize(item_path))
        quests = await api.search_quests("茶馆问讯")
        print("quests:", [x.get("name") for x in quests[:5]])
        qid = quests[0]["id"] if quests else 31416
        qdetail = await api.get_quest(qid)
        quest_path = render_quest_card(qdetail, out / "quest_demo.png")
        print("quest card:", quest_path, os.path.getsize(quest_path))
        achs = await api.search_achievements("武神重临")
        print("achs:", [(x.get("ID"), x.get("Name")) for x in achs[:5]])
        print("SMOKE_OK")
    finally:
        await http.close()


if __name__ == "__main__":
    asyncio.run(main())
