"""魔盒 API 封装。"""
from __future__ import annotations

import re
from typing import Any

from .http_client import HttpClient

NODE = "https://node.jx3box.com"
NEXT2 = "https://next2.jx3box.com"
ICON = "https://icon.jx3box.com/icon/{icon_id}.png"
ITEM_VIEW = "https://www.jx3box.com/item/view/{item_id}"
ACH_VIEW = "https://www.jx3box.com/cj/view/{ach_id}"
QUEST_VIEW = "https://www.jx3box.com/quest/view/{quest_id}"


def clean_desc(text: str | None) -> str:
    if not text:
        return ""
    s = str(text)
    s = re.sub(r"<[^>]+>", "", s)
    # 魔盒 Desc 常见：text="..." font=100
    parts = re.findall(r'text\s*=\s*"((?:\\.|[^"\\])*)"', s)
    if parts:
        s = "\n".join(parts)
    s = s.replace("\\\\n", "\n").replace("\\n", "\n").replace("\\\\", "")
    s = s.replace("text=", "").replace('"', "")
    s = re.sub(r"font=\d+", "", s)
    s = re.sub(r"\s+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def filter_name_contains(items: list[dict[str, Any]], keyword: str, name_key: str = "Name") -> list[dict[str, Any]]:
    kw = (keyword or "").strip().lower()
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    exact: list[dict[str, Any]] = []
    for it in items:
        name = str(it.get(name_key) or it.get("name") or "").strip()
        if not name or kw not in name.lower():
            continue
        key = f"{it.get('id') or it.get('ID') or name}"
        if key in seen:
            continue
        seen.add(key)
        if name.lower() == kw:
            exact.append(it)
        else:
            out.append(it)
    return exact + out


class Jx3Api:
    def __init__(self, http: HttpClient, client: str = "std") -> None:
        self.http = http
        self.client = client or "std"

    async def search_items(self, keyword: str, per: int = 50) -> list[dict[str, Any]]:
        data = await self.http.get_json(
            f"{NODE}/item/search",
            params={"keyword": keyword, "client": self.client, "per": per},
        )
        rows = (((data or {}).get("data") or {}).get("data")) or []
        return filter_name_contains(rows, keyword, "Name")

    async def get_item(self, item_id: str) -> dict[str, Any]:
        """Fetch item detail. Raises on transport/API failure; empty dict if missing body."""
        data = await self.http.get_json(
            f"{NODE}/item/{item_id}",
            params={"client": self.client},
        )
        return (((data or {}).get("data") or {}).get("item")) or {}

    async def search_achievements(self, keyword: str, per: int = 50) -> list[dict[str, Any]]:
        # search 接口更贴近关键词；失败时降级 list
        try:
            data = await self.http.get_json(
                f"{NODE}/achievement/search",
                params={"keyword": keyword, "client": self.client, "per": per},
            )
            rows = (((data or {}).get("data") or {}).get("achievements")) or []
        except Exception:
            data = await self.http.get_json(
                f"{NODE}/achievement/list",
                params={"keyword": keyword, "client": self.client, "per": per},
            )
            rows = (((data or {}).get("data") or {}).get("achievements")) or []
        return filter_name_contains(rows, keyword, "Name")

    async def search_quests(self, keyword: str, per: int = 30) -> list[dict[str, Any]]:
        data = await self.http.get_json(
            f"{NODE}/quests",
            params={"keyword": keyword, "client": self.client, "per": per},
        )
        # 兼容 list / byKeyword
        payload = data or {}
        rows = payload.get("list")
        if isinstance(rows, dict):
            rows = rows.get("byKeyword") or rows.get("list") or []
        if not isinstance(rows, list):
            rows = payload.get("data") if isinstance(payload.get("data"), list) else []
        return filter_name_contains(rows or [], keyword, "name")

    async def get_quest(self, quest_id: int | str) -> dict[str, Any]:
        data = await self.http.get_json(f"{NODE}/quest/", params={"id": quest_id})
        if not isinstance(data, dict):
            return {}
        # unwrap common envelopes: {data: {...}} / {data: {quest: {...}}}
        payload = data.get("data") if isinstance(data.get("data"), dict) else data
        if isinstance(payload, dict) and isinstance(payload.get("quest"), dict):
            payload = payload["quest"]
        if isinstance(payload, dict) and (
            "name" in payload or "QuestID" in payload or "id" in payload or "questId" in payload
        ):
            return payload
        return data if isinstance(data, dict) else {}

    async def fetch_horse_reports(self, server: str, page_size: int = 50) -> list[dict[str, Any]]:
        data = await self.http.get_json(
            f"{NEXT2}/api/game/reporter/horse",
            params={
                "pageIndex": 1,
                "pageSize": page_size,
                "server": server,
                "type": "horse",
            },
        )
        return ((((data or {}).get("data") or {}).get("list")) or [])

    async def get_icon_bytes(self, icon_id: int | str) -> bytes | None:
        try:
            return await self.http.get_bytes(ICON.format(icon_id=icon_id))
        except Exception:
            return None
