"""AstrBot 剑三魔盒查询插件。

命令：
- /物品 关键词
- /成就 关键词
- /任务 关键词
- /1 ~ /10 连续选择
- /jx3帮助
- 赤兔后台提醒（配置启用）
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

from .horse_watcher import HorseWatcher
from .http_client import HttpClient
from .jx3_api import ACH_VIEW, ITEM_VIEW, Jx3Api
from .renderers import render_help_image, render_item_tip, render_quest_card


def _norm_session_key(event: AstrMessageEvent) -> str:
    try:
        return str(event.unified_msg_origin)
    except Exception:
        return f"{event.get_platform_name()}:{event.get_group_id() or event.get_sender_id()}"


@register(
    "astrbot_plugin_jx3box",
    "云霄",
    "物品 tip / 成就链接 / 任务卡片 / 赤兔提醒",
    "1.0.0",
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
        self._horse_task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._horse: HorseWatcher | None = None

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
        self._stop.clear()
        if (self.config.get("horse") or {}).get("enabled", True):
            self._horse_task = asyncio.create_task(self._horse_loop(), name="jx3box-horse-loop")
        logger.info("astrbot_plugin_jx3box v1.0.0 已加载")

    async def terminate(self) -> None:
        self._stop.set()
        if self._horse_task and not self._horse_task.done():
            self._horse_task.cancel()
            try:
                await self._horse_task
            except asyncio.CancelledError:
                pass
        await self.http.close()
        logger.info("astrbot_plugin_jx3box 已卸载")

    # ---------------- 帮助 ----------------

    @filter.command("jx3帮助")
    async def cmd_help(self, event: AstrMessageEvent):
        """查看剑三查询帮助。"""
        path = os.path.join(self._data_dir, "cards", "help.png")
        try:
            render_help_image(path)
            yield event.chain_result([Comp.Image.fromFileSystem(path)])
        except Exception as e:
            logger.exception("render help failed")
            yield event.plain_result(
                "剑三查询帮助\n"
                "/物品 关键词  -> 物品 tip 图\n"
                "/成就 关键词  -> 成就链接\n"
                "/任务 关键词  -> 任务信息卡\n"
                "多个结果时回复 /1 /2 选择\n"
                f"帮助图生成失败：{e}"
            )

    # ---------------- 物品 ----------------

    @filter.command("物品")
    async def cmd_item(self, event: AstrMessageEvent):
        """查询物品，返回 tip 详情图。"""
        if not self.config.get("enabled", True):
            yield event.plain_result("插件已关闭。")
            return
        keyword = self._extract_arg(event, "物品")
        if not keyword:
            yield event.plain_result("用法：/物品 关键词\n例如：/物品 玄晶")
            return
        try:
            rows = await self.api.search_items(keyword)
        except Exception as e:
            logger.exception("search items failed")
            yield event.plain_result(f"查询失败：{e}")
            return
        if not rows:
            yield event.plain_result("物品名称错误")
            return
        rows = rows[:10]
        if len(rows) == 1:
            async for r in self._send_item_detail(event, rows[0]):
                yield r
            return
        self._save_choices(event, "item", rows)
        yield event.plain_result(self._format_choices(rows, name_key="Name", extra="物品"))

    # ---------------- 成就 ----------------

    @filter.command("成就")
    async def cmd_ach(self, event: AstrMessageEvent):
        """查询成就，返回链接。"""
        if not self.config.get("enabled", True):
            yield event.plain_result("插件已关闭。")
            return
        keyword = self._extract_arg(event, "成就")
        if not keyword:
            yield event.plain_result("用法：/成就 关键词\n例如：/成就 武神重临")
            return
        try:
            rows = await self.api.search_achievements(keyword)
        except Exception as e:
            logger.exception("search achievements failed")
            yield event.plain_result(f"查询失败：{e}")
            return
        if not rows:
            yield event.plain_result("成就名称错误")
            return
        rows = rows[:10]
        if len(rows) == 1:
            yield event.plain_result(self._format_ach(rows[0]))
            return
        self._save_choices(event, "achievement", rows)
        yield event.plain_result(self._format_choices(rows, name_key="Name", extra="成就"))

    # ---------------- 任务 ----------------

    @filter.command("任务")
    async def cmd_quest(self, event: AstrMessageEvent):
        """查询任务，返回信息卡图片。"""
        if not self.config.get("enabled", True):
            yield event.plain_result("插件已关闭。")
            return
        keyword = self._extract_arg(event, "任务")
        if not keyword:
            yield event.plain_result("用法：/任务 关键词\n例如：/任务 茶馆问讯")
            return
        try:
            rows = await self.api.search_quests(keyword)
        except Exception as e:
            logger.exception("search quests failed")
            yield event.plain_result(f"查询失败：{e}")
            return
        if not rows:
            yield event.plain_result("任务名称错误")
            return
        rows = rows[:10]
        if len(rows) == 1:
            async for r in self._send_quest_detail(event, rows[0]):
                yield r
            return
        self._save_choices(event, "quest", rows)
        yield event.plain_result(self._format_choices(rows, name_key="name", extra="任务"))

    # ---------------- 连续选择 /1 /2 ... ----------------

    @filter.regex(r"^/([1-9]|10)$")
    async def cmd_choose(self, event: AstrMessageEvent):
        """选择候选列表中的第 N 项。"""
        text = (event.message_str or "").strip()
        m = re.match(r"^/([1-9]|10)$", text)
        if not m:
            return
        idx = int(m.group(1)) - 1
        key = _norm_session_key(event)
        cache = self._choice_cache.get(key)
        if not cache:
            yield event.plain_result("当前没有可选列表，请先用 /物品、/成就 或 /任务 查询。")
            return
        ttl = int(self.config.get("choice_ttl_seconds", 120) or 120)
        if time.time() - float(cache.get("ts", 0)) > ttl:
            self._choice_cache.pop(key, None)
            yield event.plain_result("候选列表已过期，请重新查询。")
            return
        rows = cache.get("rows") or []
        if idx < 0 or idx >= len(rows):
            yield event.plain_result(f"序号超出范围，请输入 /1 到 /{len(rows)}")
            return
        kind = cache.get("kind")
        row = rows[idx]
        if kind == "item":
            async for r in self._send_item_detail(event, row):
                yield r
        elif kind == "achievement":
            yield event.plain_result(self._format_ach(row))
        elif kind == "quest":
            async for r in self._send_quest_detail(event, row):
                yield r
        else:
            yield event.plain_result("未知候选类型，请重新查询。")

    # ---------------- helpers ----------------

    def _extract_arg(self, event: AstrMessageEvent, cmd: str) -> str:
        text = (event.message_str or "").strip()
        # 兼容：物品 玄晶 / /物品 玄晶
        text = re.sub(rf"^/?{re.escape(cmd)}\s*", "", text).strip()
        return text

    def _save_choices(self, event: AstrMessageEvent, kind: str, rows: list[dict[str, Any]]) -> None:
        key = _norm_session_key(event)
        self._choice_cache[key] = {"kind": kind, "rows": rows, "ts": time.time()}

    def _format_choices(self, rows: list[dict[str, Any]], name_key: str, extra: str) -> str:
        lines = [f"找到多个{extra}，请回复序号选择："]
        for i, row in enumerate(rows, 1):
            name = str(row.get(name_key) or row.get("Name") or row.get("name") or "?")
            lines.append(f"{i}. {name}")
        if len(rows) >= 10:
            lines.append("最多显示 10 个，没有在里面就给出更具体的名字。")
        else:
            lines.append("没有在里面就给出更具体的名字。")
        lines.append("例如：/1")
        return "\n".join(lines)

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
            yield event.plain_result("物品数据异常。")
            return
        try:
            detail = await self.api.get_item(item_id)
            if not detail:
                detail = row
            icon_id = detail.get("IconID") or row.get("IconID")
            icon_bytes = await self.api.get_icon_bytes(icon_id) if icon_id is not None else None
            path = os.path.join(self._data_dir, "cards", f"item_{item_id.replace('/', '_')}.png")
            render_item_tip(detail, icon_bytes, path)
            yield event.chain_result([Comp.Image.fromFileSystem(path)])
        except Exception as e:
            logger.exception("item detail failed")
            name = row.get("Name") or item_id
            yield event.plain_result(f"物品详情生成失败：{e}\n{ITEM_VIEW.format(item_id=item_id)}\n{name}")

    async def _send_quest_detail(self, event: AstrMessageEvent, row: dict[str, Any]):
        qid = row.get("id") or row.get("QuestID")
        if qid is None:
            yield event.plain_result("任务数据异常。")
            return
        try:
            detail = await self.api.get_quest(qid)
            if not detail or not isinstance(detail, dict):
                detail = row
            path = os.path.join(self._data_dir, "cards", f"quest_{qid}.png")
            render_quest_card(detail, path)
            yield event.chain_result([Comp.Image.fromFileSystem(path)])
        except Exception as e:
            logger.exception("quest detail failed")
            name = row.get("name") or qid
            yield event.plain_result(f"任务卡片生成失败：{e}\n任务：{name}（ID:{qid}）")

    # ---------------- 赤兔后台 ----------------

    def _horse_cfg(self) -> dict[str, Any]:
        return self.config.get("horse") or {}

    def _target_sessions(self) -> list[str]:
        raw = (self._horse_cfg().get("target_groups") or [])
        out: list[str] = []
        for x in raw:
            s = str(x).strip()
            if not s:
                continue
            if ":" in s:
                out.append(s)
            else:
                out.append(f"aiocqhttp:GroupMessage:{s}")
        return out

    async def _push_text(self, text: str) -> None:
        sessions = self._target_sessions()
        if not sessions:
            logger.warning("赤兔提醒未配置 target_groups，消息仅记录：%s", text)
            return
        chain = MessageChain(chain=[Comp.Plain(text)])
        for session in sessions:
            try:
                await self.context.send_message(session, chain)
            except Exception:
                logger.exception("赤兔推送失败: %s", session)

    async def _horse_loop(self) -> None:
        await asyncio.sleep(3)
        while not self._stop.is_set():
            cfg = self._horse_cfg()
            if not cfg.get("enabled", True):
                await asyncio.sleep(30)
                continue
            server = str(cfg.get("server") or "飞龙在天")
            state_path = os.path.join(self._data_dir, f"horse_{server}.json")
            if self._horse is None or self._horse.server != server:
                self._horse = HorseWatcher(
                    api=self.api,
                    state_path=state_path,
                    server=server,
                    pre_alert_minutes=int(cfg.get("pre_alert_minutes", 10) or 10),
                    calibrate_before_seconds=int(cfg.get("calibrate_before_seconds", 30) or 30),
                    send_fn=self._push_text,
                )
            try:
                await self._horse.tick()
            except Exception:
                logger.exception("horse tick failed")
            # 已锁定后主要本地等；未锁定按 poll_idle_seconds
            locked = bool(self._horse and self._horse.state.locked and not self._horse.state.pushed_refresh)
            interval = 5 if locked else int(cfg.get("poll_idle_seconds", 300) or 300)
            interval = max(3, interval)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass
