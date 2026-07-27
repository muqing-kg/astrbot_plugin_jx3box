"""赤兔订阅：区服名单匹配与群订阅持久化。"""
from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

TZ = timezone(timedelta(hours=8))

DEFAULT_SERVER_LIST_URLS = (
    "https://cdn.jsdelivr.net/gh/JX3BOX/jx3box-data@master/data/server/server_list.json",
    "https://cdn.jsdelivr.net/npm/@jx3box/jx3box-data/data/server/server_list.json",
    "https://raw.githubusercontent.com/JX3BOX/jx3box-data/master/data/server/server_list.json",
)

# 与 jx3box-data server_list 同步的兜底名单（本地/CDN 都失败时使用）
FALLBACK_SERVERS = [
    "缘起稻香",
    "天宝盛世",
    "剑啸江湖",
    "蝶恋花",
    "龙争虎斗",
    "长安城",
    "幽月轮",
    "斗转星移",
    "剑胆琴心",
    "乾坤一掷",
    "唯我独尊",
    "梦江南",
    "绝代天骄",
    "天鹅坪",
    "破阵子",
    "飞龙在天",
    "眉间雪",
    "山海相逢",
    "共結來緣",
    "傲血戰意",
    "巔峰再起",
    "江海雲夢",
]


def now_iso() -> str:
    return datetime.now(TZ).isoformat()


def _norm_name(s: str) -> str:
    return "".join(str(s or "").split()).casefold()


class HorseSubscriptionStore:
    """Persist group <-> server subscriptions.

    One record = one group subscribes one server.
    A group may own many servers; a server may fan out to many groups.
    """

    def __init__(
        self,
        path: str,
        bundled_server_list: str | None = None,
        server_list_cache: str | None = None,
    ) -> None:
        self.path = path
        self.bundled_server_list = bundled_server_list or ""
        # Prefer writing refreshed names into data dir (writable), not package assets.
        self.server_list_cache = server_list_cache or ""
        self._lock = threading.RLock()
        self._servers: list[str] = []
        self._server_index: dict[str, str] = {}
        self._rows: list[dict[str, Any]] = []
        self._load_servers_local()
        self._load_rows()

    def _set_servers(self, names: list[str]) -> None:
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in names:
            name = str(raw or "").strip()
            if not name:
                continue
            key = _norm_name(name)
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(name)
        if not cleaned:
            cleaned = list(FALLBACK_SERVERS)
        self._servers = cleaned
        self._server_index = {_norm_name(x): x for x in cleaned}

    def _load_servers_local(self) -> None:
        names: list[str] = []
        for path in (self.server_list_cache, self.bundled_server_list):
            if not path or not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list) and data:
                    names = [str(x) for x in data]
                    break
            except Exception:
                continue
        self._set_servers(names or list(FALLBACK_SERVERS))

    def _persist_servers(self) -> None:
        targets: list[str] = []
        if self.server_list_cache:
            targets.append(self.server_list_cache)
        if self.bundled_server_list:
            targets.append(self.bundled_server_list)
        payload = self._servers
        for path in targets:
            try:
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                    f.write("\n")
            except Exception:
                continue

    async def refresh_servers(self, http: Any | None = None) -> list[str]:
        if http is None:
            return list(self._servers)
        for url in DEFAULT_SERVER_LIST_URLS:
            try:
                data = await http.get_json(url)
            except Exception:
                continue
            if isinstance(data, list) and data:
                self._set_servers([str(x) for x in data])
                self._persist_servers()
                return list(self._servers)
        return list(self._servers)

    def list_servers(self) -> list[str]:
        return list(self._servers)

    def match_server(self, raw: str) -> str | None:
        text = str(raw or "").strip()
        if not text:
            return None
        hit = self._server_index.get(_norm_name(text))
        if hit:
            return hit
        key = _norm_name(text)
        partial = [s for s in self._servers if key and key in _norm_name(s)]
        if len(partial) == 1:
            return partial[0]
        return None

    def _load_rows(self) -> None:
        rows: list[dict[str, Any]] = []
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                raw = data.get("subscriptions") if isinstance(data, dict) else data
                if isinstance(raw, list):
                    for item in raw:
                        if not isinstance(item, dict):
                            continue
                        server = str(item.get("server") or "").strip()
                        group_id = str(item.get("group_id") or "").strip()
                        session = str(item.get("session") or "").strip()
                        if not server or not (group_id or session):
                            continue
                        rows.append(
                            {
                                "group_id": group_id,
                                "session": session
                                or (f"aiocqhttp:GroupMessage:{group_id}" if group_id else ""),
                                "platform": str(item.get("platform") or "").strip(),
                                "server": server,
                                "created_at": str(item.get("created_at") or now_iso()),
                            }
                        )
            except Exception:
                rows = []
        self._rows = self._dedupe(rows)

    def _dedupe(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            server = str(row.get("server") or "").strip()
            group_id = str(row.get("group_id") or "").strip()
            session = str(row.get("session") or "").strip()
            if not server:
                continue
            gkey = group_id or session
            if not gkey:
                continue
            key = (gkey, server)
            if key in merged:
                continue
            merged[key] = {
                "group_id": group_id,
                "session": session
                or (f"aiocqhttp:GroupMessage:{group_id}" if group_id else ""),
                "platform": str(row.get("platform") or "").strip(),
                "server": server,
                "created_at": str(row.get("created_at") or now_iso()),
            }
        out = list(merged.values())
        out.sort(
            key=lambda r: (
                str(r.get("created_at") or ""),
                str(r.get("group_id") or r.get("session") or ""),
                str(r.get("server") or ""),
            )
        )
        return out

    def _save_unlocked(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        payload = {"subscriptions": self._rows, "updated_at": now_iso()}
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, self.path)

    def reload(self) -> None:
        with self._lock:
            self._load_rows()

    def list_all(self) -> list[dict[str, Any]]:
        with self._lock:
            return deepcopy(self._rows)

    def list_for_group(self, group_id: str = "", session: str = "") -> list[dict[str, Any]]:
        gid = str(group_id or "").strip()
        sess = str(session or "").strip()
        with self._lock:
            out = []
            for row in self._rows:
                if gid and row.get("group_id") == gid:
                    out.append(deepcopy(row))
                elif (not gid) and sess and row.get("session") == sess:
                    out.append(deepcopy(row))
            return out

    def servers_with_subscribers(self) -> list[str]:
        with self._lock:
            seen: list[str] = []
            bag: set[str] = set()
            for row in self._rows:
                server = str(row.get("server") or "").strip()
                if server and server not in bag:
                    bag.add(server)
                    seen.append(server)
            return seen

    def groups_for_server(self, server: str) -> list[str]:
        name = str(server or "").strip()
        if not name:
            return []
        with self._lock:
            out: list[str] = []
            bag: set[str] = set()
            for row in self._rows:
                if str(row.get("server") or "").strip() != name:
                    continue
                session = str(row.get("session") or "").strip()
                if not session:
                    gid = str(row.get("group_id") or "").strip()
                    if gid:
                        session = f"aiocqhttp:GroupMessage:{gid}"
                if session and session not in bag:
                    bag.add(session)
                    out.append(session)
            return out

    def subscribe(
        self,
        *,
        server: str,
        group_id: str,
        session: str,
        platform: str = "",
    ) -> tuple[bool, str, dict[str, Any] | None]:
        official = self.match_server(server)
        if not official:
            return False, "请输入正确区服！", None
        gid = str(group_id or "").strip()
        sess = str(session or "").strip()
        if not gid and not sess:
            return False, "只能在群聊中订阅赤兔提醒。", None
        if not sess and gid:
            sess = f"aiocqhttp:GroupMessage:{gid}"
        with self._lock:
            for row in self._rows:
                same_group = (gid and row.get("group_id") == gid) or (
                    (not gid) and sess and row.get("session") == sess
                )
                if same_group and row.get("server") == official:
                    return False, f"本群已订阅区服：{official}", deepcopy(row)
            row = {
                "group_id": gid,
                "session": sess,
                "platform": str(platform or "").strip(),
                "server": official,
                "created_at": now_iso(),
            }
            self._rows.append(row)
            self._rows = self._dedupe(self._rows)
            self._save_unlocked()
            saved = next(
                (
                    r
                    for r in self._rows
                    if r.get("server") == official
                    and (
                        (gid and r.get("group_id") == gid)
                        or ((not gid) and r.get("session") == sess)
                    )
                ),
                row,
            )
            return True, f"订阅成功：本群已监听区服【{official}】", deepcopy(saved)

    def unsubscribe_index(self, index: int) -> tuple[bool, str, dict[str, Any] | None]:
        with self._lock:
            if index < 1 or index > len(self._rows):
                return False, f"序号超出范围，当前共 {len(self._rows)} 条订阅。", None
            row = self._rows.pop(index - 1)
            self._save_unlocked()
            return True, "已删除订阅", deepcopy(row)

    def signature_for_server(self, server: str) -> tuple[str, ...]:
        return tuple(self.groups_for_server(server))
