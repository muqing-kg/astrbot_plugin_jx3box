"""AstrBot 剑三魔盒查询插件。

命令（带不带 / 均可）：
- 物品 关键词
- 成就 关键词
- 任务 关键词
- 多个结果直接回复数字选择；超过 10 条出图，回复 换页 翻页
- jx3帮助
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, StarTools, register
import astrbot.api.message_components as Comp

from .api.http_client import HttpClient
from .api.jx3_api import ACH_VIEW, ITEM_VIEW, Jx3Api
from .render.choice_list import (
    KIND_LABELS,
    PAGE_SIZE,
    TEXT_THRESHOLD,
    choice_footer,
    format_choice_text,
    name_key_for_kind,
    page_slice,
    render_choice_list_image,
    row_icon_id,
    total_pages,
)
from .render.renderers import render_help_image
from .render.tip_html import render_item_tip_html
from .render.quest_html import render_quest_card_html, resolve_quest_item_meta


def _user_error(prefix: str = "操作失败，请稍后重试。") -> str:
    """Short user-facing error; details go to logs only."""
    return prefix


def _norm_session_key(event: AstrMessageEvent) -> str:
    try:
        return str(event.unified_msg_origin)
    except Exception:
        return f"{event.get_platform_name()}:{event.get_group_id() or event.get_sender_id()}"


@register(
    "astrbot_plugin_jx3box",
    "沐沐沐倾",
    "物品 tip / 成就链接 / 任务卡片",
    "1.0.2",
)
class Jx3BoxPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.context = context
        self.config = config
        self.http = HttpClient(timeout=25)
        self.api = Jx3Api(self.http, client=str(config.get("client", "std") or "std"))
        self._data_dir = self._resolve_data_dir()
        self._choice_cache: dict[str, dict[str, Any]] = {}

    async def _reply_plain(self, event: AstrMessageEvent, text: str) -> None:
        await self._reply_chain(event, [Comp.Plain(text)])

    async def _reply_chain(self, event: AstrMessageEvent, comps: list) -> None:
        """直发消息：不经 AstrBot 结果装饰（无 @ / 引用 / 前缀 / 分段等任何附加）。"""
        chain = MessageChain(chain=comps)
        try:
            await event.send(chain)
        except Exception:
            logger.exception("direct send failed, fallback to context.send_message")
            try:
                await self.context.send_message(str(event.unified_msg_origin), chain)
            except Exception:
                logger.exception("fallback send failed")
        try:
            event.stop_event()
        except Exception:
            pass

    def _resolve_data_dir(self) -> str:
        try:
            data_dir = StarTools.get_data_dir("astrbot_plugin_jx3box")
            path = str(data_dir)
        except Exception:
            path = os.path.join(os.path.dirname(__file__), "data")
        os.makedirs(path, exist_ok=True)
        os.makedirs(os.path.join(path, "cards"), exist_ok=True)
        return path

    async def initialize(self) -> None:
        await self.http.start()
        logger.info("astrbot_plugin_jx3box v1.0.2 已加载")

    async def terminate(self) -> None:
        await self.http.close()
        logger.info("astrbot_plugin_jx3box 已卸载")

    # ---------------- 帮助 ----------------

    @filter.regex(r"^/?jx3帮助(?:\s|$)")
    async def cmd_help(self, event: AstrMessageEvent):
        """查看剑三查询帮助。"""
        path = os.path.join(self._data_dir, "cards", "help.png")
        try:
            render_help_image(path)
            await self._reply_chain(event, [Comp.Image.fromFileSystem(path)])
        except Exception:
            logger.exception("render help failed")
            await self._reply_plain(event, 
                "剑三查询帮助\n"
                "物品 关键词  -> 物品 tip 图\n"
                "成就 关键词  -> 成就链接\n"
                "任务 关键词  -> 任务信息卡\n"
                "命令带不带 / 均可；多个结果直接回复数字，超过 10 条回复 换页\n"
                "帮助图生成失败，请稍后重试。"
            )

    # ---------------- 物品 ----------------

    @filter.regex(r"^/?物品(?:\s|$)")
    async def cmd_item(self, event: AstrMessageEvent):
        """查询物品，返回 tip 详情图。"""
        keyword = self._extract_arg(event, "物品")
        if not keyword:
            await self._reply_plain(event, "用法：物品 关键词\n例如：物品 玄晶")
            return
        try:
            rows = await self.api.search_items(keyword, per=200)
        except Exception:
            logger.exception("search items failed")
            await self._reply_plain(event, _user_error("查询失败，请稍后重试。"))
            return
        if not rows:
            await self._reply_plain(event, "物品名称错误")
            return
        if len(rows) == 1:
            await self._send_item_detail(event, rows[0])
            return
        await self._emit_choices(event, kind="item", rows=rows)

    # ---------------- 成就 ----------------

    @filter.regex(r"^/?成就(?:\s|$)")
    async def cmd_ach(self, event: AstrMessageEvent):
        """查询成就，返回链接。"""
        keyword = self._extract_arg(event, "成就")
        if not keyword:
            await self._reply_plain(event, "用法：成就 关键词\n例如：成就 武神重临")
            return
        try:
            rows = await self.api.search_achievements(keyword, per=200)
        except Exception:
            logger.exception("search achievements failed")
            await self._reply_plain(event, _user_error("查询失败，请稍后重试。"))
            return
        if not rows:
            await self._reply_plain(event, "成就名称错误")
            return
        if len(rows) == 1:
            await self._reply_plain(event, self._format_ach(rows[0]))
            return
        await self._emit_choices(event, kind="achievement", rows=rows)

    # ---------------- 任务 ----------------

    @filter.regex(r"^/?任务(?:\s|$)")
    async def cmd_quest(self, event: AstrMessageEvent):
        """查询任务，返回信息卡图片。"""
        keyword = self._extract_arg(event, "任务")
        if not keyword:
            await self._reply_plain(event, "用法：任务 关键词\n例如：任务 茶馆问讯")
            return
        try:
            rows = await self.api.search_quests(keyword, per=200)
        except Exception:
            logger.exception("search quests failed")
            await self._reply_plain(event, _user_error("查询失败，请稍后重试。"))
            return
        if not rows:
            await self._reply_plain(event, "任务名称错误")
            return
        if len(rows) == 1:
            await self._send_quest_detail(event, rows[0])
            return
        await self._emit_choices(event, kind="quest", rows=rows)

    # ---------------- 连续选择：数字 / 换页 ----------------

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def cmd_choose(self, event: AstrMessageEvent):
        """选择候选或换页。

        兼容：
        - 12 / /12  选择第 N 项
        - 换页 / 下一页
        仅当当前会话存在有效候选列表时才接管，避免误伤普通聊天。
        """
        text = (event.message_str or "").strip()
        is_page = text in {"换页", "下一页", "/换页", "/下一页"}
        m = re.match(r"^/?([1-9]\d{0,3})$", text)
        if not is_page and not m:
            return

        cache = None
        key = ""
        for k in self._choice_keys(event):
            if k and k in self._choice_cache:
                key = str(k)
                cache = self._choice_cache[key]
                break
        if not cache:
            return

        ttl = int(self.config.get("choice_ttl_seconds", 120) or 120)
        if time.time() - float(cache.get("ts", 0)) > ttl:
            self._choice_cache.pop(key, None)
            try:
                event.stop_event()
            except Exception:
                pass
            await self._reply_plain(event, "候选列表已过期，请重新查询。")
            return

        try:
            event.stop_event()
        except Exception:
            pass

        rows = cache.get("rows") or []
        kind = str(cache.get("kind") or "")
        page = int(cache.get("page") or 1)
        pages = total_pages(len(rows))

        if is_page:
            if pages <= 1 or page >= pages:
                await self._reply_plain(event, "已经是最后一页")
                return
            page += 1
            cache["page"] = page
            cache["ts"] = time.time()
            # keep all mirrored keys in sync
            for k in list(self._choice_keys(event)):
                if k in self._choice_cache:
                    self._choice_cache[k] = cache
            await self._send_choice_page(event, kind=kind, rows=rows, page=page)
            return

        idx = int(m.group(1)) - 1
        if idx < 0 or idx >= len(rows):
            await self._reply_plain(event, f"序号超出范围，请输入 1 到 {len(rows)}")
            return

        row = rows[idx]
        logger.info(
            "jx3box choose: session=%s kind=%s idx=%s name=%s",
            key,
            kind,
            idx + 1,
            row.get("Name") or row.get("name"),
        )
        for k in list(self._choice_keys(event)):
            self._choice_cache.pop(k, None)
        self._choice_cache.pop(key, None)
        if kind == "item":
            await self._send_item_detail(event, row)
        elif kind == "achievement":
            await self._reply_plain(event, self._format_ach(row))
        elif kind == "quest":
            await self._send_quest_detail(event, row)
        else:
            await self._reply_plain(event, "未知候选类型，请重新查询。")

    # ---------------- helpers ----------------

    def _extract_arg(self, event: AstrMessageEvent, cmd: str) -> str:
        text = (event.message_str or "").strip()
        # 兼容：物品 玄晶 / /物品 玄晶
        text = re.sub(rf"^/?{re.escape(cmd)}\s*", "", text).strip()
        return text

    def _choice_keys(self, event: AstrMessageEvent) -> list[str]:
        """Build session keys for choice cache.

        Isolation rules:
        - group chat: only group-scoped keys (never bare user id)
        - private chat: user-scoped keys are allowed
        This prevents /1 selection from leaking across groups.
        """
        keys: list[str] = []

        def _add(v: str) -> None:
            s = str(v or "").strip()
            if s and s not in keys:
                keys.append(s)

        _add(_norm_session_key(event))
        try:
            _add(str(event.unified_msg_origin))
        except Exception:
            pass

        gid = ""
        try:
            gid = str(event.get_group_id() or "").strip()
        except Exception:
            gid = ""

        platform = ""
        try:
            platform = str(event.get_platform_name() or "").strip()
        except Exception:
            platform = ""

        uid = ""
        try:
            uid = str(event.get_sender_id() or "").strip()
        except Exception:
            uid = ""

        if gid:
            # Prefer per-user keys so two members in one group do not share /1 lists.
            if uid:
                _add(f"group:{gid}:user:{uid}")
                if platform:
                    _add(f"{platform}:GroupMessage:{gid}:user:{uid}")
            # Shared group keys remain as fallback for clients without stable sender id.
            _add(f"group:{gid}")
            if platform:
                _add(f"{platform}:GroupMessage:{gid}")
        else:
            # private chat only
            if uid:
                _add(f"user:{uid}")
                if platform:
                    _add(f"{platform}:FriendMessage:{uid}")

        return keys

    def _save_choices(
        self,
        event: AstrMessageEvent,
        kind: str,
        rows: list[dict[str, Any]],
        *,
        page: int = 1,
    ) -> None:
        payload = {
            "kind": kind,
            "rows": rows,
            "page": max(1, int(page or 1)),
            "ts": time.time(),
        }
        keys = self._choice_keys(event)
        # Write per-user keys first; if none, fall back to all keys (private / no uid).
        preferred = [k for k in keys if ":user:" in k or k.startswith("user:")]
        targets = preferred or keys
        for key in targets:
            self._choice_cache[key] = payload

    def _format_choices(self, rows: list[dict[str, Any]], name_key: str, extra: str) -> str:
        return format_choice_text(rows, kind_label=extra, name_key=name_key)

    async def _emit_choices(self, event: AstrMessageEvent, *, kind: str, rows: list[dict[str, Any]]):
        """2..10 text list; >=11 full image list (page 1)."""
        label = KIND_LABELS.get(kind, "结果")
        name_key = name_key_for_kind(kind)
        if len(rows) <= TEXT_THRESHOLD:
            self._save_choices(event, kind, rows, page=1)
            await self._reply_plain(event, self._format_choices(rows, name_key=name_key, extra=label))
            return
        self._save_choices(event, kind, rows, page=1)
        await self._send_choice_page(event, kind=kind, rows=rows, page=1)

    async def _collect_choice_icons(self, rows: list[dict[str, Any]]) -> dict[str, bytes]:
        ids: list[str] = []
        seen: set[str] = set()
        for row in rows:
            iid = row_icon_id(row)
            if not iid or iid in seen:
                continue
            seen.add(iid)
            ids.append(iid)
        if not ids:
            return {}
        sem = asyncio.Semaphore(8)
        out: dict[str, bytes] = {}

        async def _one(iid: str) -> None:
            async with sem:
                try:
                    raw = await self.api.get_icon_bytes(iid)
                except Exception:
                    raw = None
                if raw:
                    out[iid] = raw

        await asyncio.gather(*(_one(i) for i in ids))
        return out

    async def _send_choice_page(
        self,
        event: AstrMessageEvent,
        *,
        kind: str,
        rows: list[dict[str, Any]],
        page: int,
    ):
        page_rows, page_n, pages = page_slice(rows, page)
        out = os.path.join(
            self._data_dir,
            "cards",
            "choices",
            f"{kind}_p{page_n}_{int(time.time())}.png",
        )
        try:
            icons = await self._collect_choice_icons(page_rows)
            path = render_choice_list_image(
                rows,
                kind=kind,
                page=page_n,
                out_path=out,
                icon_bytes_map=icons,
            )
            await self._reply_chain(event, [Comp.Image.fromFileSystem(path)])
        except Exception:
            logger.exception("choice list image failed")
            # text fallback for current page only
            label = KIND_LABELS.get(kind, "结果")
            name_key = name_key_for_kind(kind)
            lines = [f"找到 {len(rows)} 个{label} · 第 {page_n}/{max(pages, 1)} 页（图片生成失败，文字版）"]
            base = (page_n - 1) * PAGE_SIZE
            for i, row in enumerate(page_rows, 1):
                name = str(row.get(name_key) or row.get("Name") or row.get("name") or "?")
                lines.append(f"{base + i}. {name}")
            lines.append(choice_footer(is_last=(pages <= 1 or page_n >= pages)))
            await self._reply_plain(event, "\n".join(lines))

    def _format_ach(self, row: dict[str, Any]) -> str:
        ach_id = row.get("ID") or row.get("id")
        name = row.get("Name") or row.get("name") or "未知成就"
        desc = row.get("ShortDesc") or row.get("Desc") or ""
        url = ACH_VIEW.format(ach_id=ach_id)
        lines = [f"成就：{name}", url]
        if desc:
            lines.append(str(desc))
        return "\n".join(lines)

    async def _send_item_detail(self, event: AstrMessageEvent, row: dict[str, Any]):
        item_id = str(row.get("id") or "")
        if not item_id:
            await self._reply_plain(event, "物品数据异常。")
            return
        try:
            try:
                detail = await self.api.get_item(item_id)
            except Exception:
                logger.exception("get_item failed id=%s", item_id)
                detail = {}
            if not detail:
                detail = row
            # HTML multi-template tip via AstrBot html_render -> astrbot-t2i
            img = await render_item_tip_html(self, detail, return_url=False)
            img_s = str(img or "")
            if img_s.startswith("http://") or img_s.startswith("https://"):
                await self._reply_chain(event, [Comp.Image.fromURL(img_s)])
            else:
                await self._reply_chain(event, [Comp.Image.fromFileSystem(img_s)])
        except Exception:
            logger.exception("item detail failed")
            name = row.get("Name") or item_id
            url = ITEM_VIEW.format(item_id=item_id)
            await self._reply_plain(event, 
                "物品详情渲染失败，请稍后重试。" + chr(10) + url + chr(10) + str(name)
            )

    async def _send_quest_detail(self, event: AstrMessageEvent, row: dict[str, Any]):
        qid = row.get("id") or row.get("QuestID")
        if qid is None:
            await self._reply_plain(event, "任务数据异常。")
            return
        try:
            try:
                detail = await self.api.get_quest(qid)
            except Exception:
                logger.exception("get_quest failed id=%s", qid)
                detail = {}
            if not detail or not isinstance(detail, dict):
                detail = row
            # nested data unwrap (API already unwraps; keep for search-row fallback)
            if "name" not in detail and isinstance(detail.get("data"), dict):
                detail = detail.get("data") or detail
            item_meta = await resolve_quest_item_meta(self.api, detail)
            img = await render_quest_card_html(self, detail, item_meta=item_meta, return_url=False)
            img_s = str(img or "")
            if img_s.startswith("http://") or img_s.startswith("https://"):
                await self._reply_chain(event, [Comp.Image.fromURL(img_s)])
            else:
                await self._reply_chain(event, [Comp.Image.fromFileSystem(img_s)])
        except Exception:
            logger.exception("quest detail failed")
            name = row.get("name") or qid
            await self._reply_plain(event, 
                "任务卡片渲染失败，请稍后重试。" + chr(10) + f"任务：{name}（ID:{qid}）"
            )
