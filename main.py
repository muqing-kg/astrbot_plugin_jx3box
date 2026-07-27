"""AstrBot 剑三魔盒查询插件。

命令：
- /物品 关键词
- /成就 关键词
- /任务 关键词
- /1 ~ /10 连续选择
- /jx3帮助
- /赤兔订阅 区服
- /赤兔查询（管理员）
- /赤兔删除 序号（管理员）
- 赤兔后台按群订阅推送
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

from .horse_subscribe import HorseSubscriptionStore
from .horse_watcher import HorseWatcher
from .http_client import HttpClient
from .jx3_api import ACH_VIEW, ITEM_VIEW, Jx3Api
from .renderers import render_help_image
from .tip_html import render_item_tip_html
from .quest_html import render_quest_card_html, resolve_quest_item_meta


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
    "物品 tip / 成就链接 / 任务卡片 / 赤兔提醒",
    "1.0.1",
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
        self._horses: dict[str, HorseWatcher] = {}
        self._horse_subs = HorseSubscriptionStore(
            path=os.path.join(self._data_dir, "horse_subscriptions.json"),
            bundled_server_list=os.path.join(
                os.path.dirname(__file__), "assets", "server_list.json"
            ),
            server_list_cache=os.path.join(self._data_dir, "server_list.json"),
        )

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
        try:
            await self._horse_subs.refresh_servers(self.http)
        except Exception:
            logger.exception("refresh jx3 server list failed; using bundled list")
        if (self.config.get("horse") or {}).get("enabled", True):
            self._horse_task = asyncio.create_task(self._horse_loop(), name="jx3box-horse-loop")
        logger.info("astrbot_plugin_jx3box v1.0.1 已加载")

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
        except Exception:
            logger.exception("render help failed")
            yield event.plain_result(
                "剑三查询帮助\n"
                "/物品 关键词  -> 物品 tip 图\n"
                "/成就 关键词  -> 成就链接\n"
                "/任务 关键词  -> 任务信息卡\n"
                "多个结果时回复 /1 /2 选择\n"
                "/赤兔订阅 区服  -> 本群订阅赤兔\n"
                "帮助图生成失败，请稍后重试。"
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
        except Exception:
            logger.exception("search items failed")
            yield event.plain_result(_user_error("查询失败，请稍后重试。"))
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
        except Exception:
            logger.exception("search achievements failed")
            yield event.plain_result(_user_error("查询失败，请稍后重试。"))
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
        except Exception:
            logger.exception("search quests failed")
            yield event.plain_result(_user_error("查询失败，请稍后重试。"))
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

    # ---------------- 连续选择 /1 /2 ... 或 1 / 2 ... ----------------

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def cmd_choose(self, event: AstrMessageEvent):
        """选择候选列表中的第 N 项。

        兼容：
        - /1
        - 1
        仅当当前会话存在有效候选列表时才接管，避免误伤普通聊天。
        """
        text = (event.message_str or "").strip()
        m = re.match(r"^/?([1-9]|10)$", text)
        if not m:
            return

        cache = None
        key = ""
        for k in self._choice_keys(event):
            if k and k in self._choice_cache:
                key = str(k)
                cache = self._choice_cache[key]
                break
        if not cache:
            # 没有候选时不拦截，交给其他插件/AI
            return

        ttl = int(self.config.get("choice_ttl_seconds", 120) or 120)
        if time.time() - float(cache.get("ts", 0)) > ttl:
            self._choice_cache.pop(key, None)
            try:
                event.stop_event()
            except Exception:
                pass
            yield event.plain_result("候选列表已过期，请重新查询。")
            return

        idx = int(m.group(1)) - 1
        rows = cache.get("rows") or []
        if idx < 0 or idx >= len(rows):
            try:
                event.stop_event()
            except Exception:
                pass
            yield event.plain_result(f"序号超出范围，请输入 /1 到 /{len(rows)}")
            return

        # 关键：先截断事件，防止 AngelHeart/LLM 抢走
        try:
            event.stop_event()
        except Exception:
            pass

        kind = cache.get("kind")
        row = rows[idx]
        logger.info(
            "jx3box choose: session=%s kind=%s idx=%s name=%s",
            key,
            kind,
            idx + 1,
            row.get("Name") or row.get("name"),
        )
        # drop cache after a valid pick to avoid repeated /n re-render in TTL
        for k in list(self._choice_keys(event)):
            self._choice_cache.pop(k, None)
        self._choice_cache.pop(key, None)
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

    def _save_choices(self, event: AstrMessageEvent, kind: str, rows: list[dict[str, Any]]) -> None:
        payload = {"kind": kind, "rows": rows, "ts": time.time()}
        keys = self._choice_keys(event)
        # Write per-user keys first; if none, fall back to all keys (private / no uid).
        preferred = [k for k in keys if ":user:" in k or k.startswith("user:")]
        targets = preferred or keys
        for key in targets:
            self._choice_cache[key] = payload

    def _format_choices(self, rows: list[dict[str, Any]], name_key: str, extra: str) -> str:
        lines = [f"找到多个{extra}，请回复序号选择："]
        for i, row in enumerate(rows, 1):
            name = str(row.get(name_key) or row.get("Name") or row.get("name") or "?")
            lines.append(f"{i}. {name}")
        if len(rows) >= 10:
            lines.append("最多显示 10 个，没有在里面就给出更具体的名字。")
        else:
            lines.append("没有在里面就给出更具体的名字。")
        lines.append("直接回复：/1  或  1")
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
                if hasattr(event, "image_result"):
                    yield event.image_result(img_s)
                else:
                    yield event.chain_result([Comp.Image.fromURL(img_s)])
            else:
                yield event.chain_result([Comp.Image.fromFileSystem(img_s)])
        except Exception:
            logger.exception("item detail failed")
            name = row.get("Name") or item_id
            url = ITEM_VIEW.format(item_id=item_id)
            yield event.plain_result(
                "物品详情渲染失败，请稍后重试。" + chr(10) + url + chr(10) + str(name)
            )

    async def _send_quest_detail(self, event: AstrMessageEvent, row: dict[str, Any]):
        qid = row.get("id") or row.get("QuestID")
        if qid is None:
            yield event.plain_result("任务数据异常。")
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
                if hasattr(event, "image_result"):
                    yield event.image_result(img_s)
                else:
                    yield event.chain_result([Comp.Image.fromURL(img_s)])
            else:
                yield event.chain_result([Comp.Image.fromFileSystem(img_s)])
        except Exception:
            logger.exception("quest detail failed")
            name = row.get("name") or qid
            yield event.plain_result(
                "任务卡片渲染失败，请稍后重试。" + chr(10) + f"任务：{name}（ID:{qid}）"
            )

    # ---------------- 赤兔命令 / 后台 ----------------

    def _horse_cfg(self) -> dict[str, Any]:
        return self.config.get("horse") or {}

    def _is_admin(self, event: AstrMessageEvent) -> bool:
        try:
            if hasattr(event, "is_admin") and callable(event.is_admin):
                return bool(event.is_admin())
        except Exception:
            pass
        try:
            role = str(event.role or "").lower()
            if role in {"owner", "admin", "administrator"}:
                return True
        except Exception:
            pass
        return False

    def _event_group_id(self, event: AstrMessageEvent) -> str:
        try:
            return str(event.get_group_id() or "").strip()
        except Exception:
            return ""

    def _event_platform(self, event: AstrMessageEvent) -> str:
        try:
            return str(event.get_platform_name() or "").strip()
        except Exception:
            return ""

    def _event_group_session(self, event: AstrMessageEvent) -> str:
        gid = self._event_group_id(event)
        platform = self._event_platform(event) or "aiocqhttp"
        if gid:
            return f"{platform}:GroupMessage:{gid}"
        try:
            return str(event.unified_msg_origin or "").strip()
        except Exception:
            return ""

    def _normalize_session(self, raw: str) -> str:
        s = str(raw or "").strip()
        if not s:
            return ""
        if ":" in s:
            return s
        return f"aiocqhttp:GroupMessage:{s}"

    def _sessions_from_groups(self, groups: list[str]) -> list[str]:
        out: list[str] = []
        for x in groups or []:
            s = self._normalize_session(str(x))
            if s and s not in out:
                out.append(s)
        return out

    def _format_sub_rows(self, rows: list[dict[str, Any]], *, title: str) -> str:
        if not rows:
            return title + "\n（空）"
        lines = [title, f"共 {len(rows)} 条："]
        for i, row in enumerate(rows, 1):
            gid = str(row.get("group_id") or "").strip() or "-"
            server = str(row.get("server") or "").strip() or "-"
            lines.append(f"{i}. 群 {gid} ｜ 区服 {server}")
        return "\n".join(lines)

    @filter.command("赤兔订阅")
    async def cmd_horse_sub(self, event: AstrMessageEvent):
        """当前群订阅某个区服的赤兔提醒。"""
        if not self.config.get("enabled", True):
            yield event.plain_result("插件已关闭。")
            return
        if not (self.config.get("horse") or {}).get("enabled", True):
            yield event.plain_result("赤兔提醒未启用。")
            return
        gid = self._event_group_id(event)
        if not gid:
            yield event.plain_result("只能在群聊中订阅赤兔提醒。")
            return
        server_raw = self._extract_arg(event, "赤兔订阅")
        if not server_raw:
            yield event.plain_result("用法：/赤兔订阅 区服名\n例如：/赤兔订阅 梦江南")
            return
        session = self._event_group_session(event)
        ok, msg, _row = self._horse_subs.subscribe(
            server=server_raw,
            group_id=gid,
            session=session,
            platform=self._event_platform(event),
        )
        if ok:
            mine = self._horse_subs.list_for_group(group_id=gid, session=session)
            servers = "、".join(r.get("server") or "?" for r in mine) or "-"
            yield event.plain_result(f"{msg}\n本群当前订阅：{servers}")
        else:
            yield event.plain_result(msg)

    @filter.command("赤兔查询")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def cmd_horse_query(self, event: AstrMessageEvent):
        """管理员查看全部群的赤兔订阅。"""
        rows = self._horse_subs.list_all()
        text = self._format_sub_rows(rows, title="赤兔订阅一览")
        if rows:
            text += "\n删除：/赤兔删除 序号"
        yield event.plain_result(text)

    @filter.command("赤兔删除")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def cmd_horse_delete(self, event: AstrMessageEvent):
        """管理员按序号删除一条订阅。"""
        raw = self._extract_arg(event, "赤兔删除").strip()
        if not raw:
            rows = self._horse_subs.list_all()
            yield event.plain_result(
                self._format_sub_rows(rows, title="请带序号删除，例如：/赤兔删除 1")
            )
            return
        m = re.search(r"(\d+)", raw)
        if not m:
            yield event.plain_result("用法：/赤兔删除 序号\n先用 /赤兔查询 看序号。")
            return
        idx = int(m.group(1))
        ok, msg, row = self._horse_subs.unsubscribe_index(idx)
        if not ok or not row:
            yield event.plain_result(msg)
            return
        gid = str(row.get("group_id") or "-")
        server = str(row.get("server") or "-")
        yield event.plain_result(f"{msg}\n{idx}. 群 {gid} ｜ 区服 {server}")

    async def _push_text_to(self, text: str, groups: list[str], server: str = "") -> None:
        # Hard isolation: only explicit sessions for this server subscription set.
        sessions = self._sessions_from_groups(list(groups or []))
        if not sessions:
            logger.warning(
                "赤兔推送无订阅群（server=%s），仅记录：%s",
                server or "?",
                text,
            )
            return
        chain = MessageChain(chain=[Comp.Plain(text)])
        for session in sessions:
            try:
                await self.context.send_message(session, chain)
            except Exception:
                logger.exception("赤兔推送失败 server=%s session=%s", server, session)

    async def _horse_loop(self) -> None:
        await asyncio.sleep(3)
        while not self._stop.is_set():
            cfg = self._horse_cfg()
            if not cfg.get("enabled", True):
                await asyncio.sleep(30)
                continue

            # always reload disk subscriptions so command changes apply quickly
            try:
                self._horse_subs.reload()
            except Exception:
                logger.exception("reload horse subscriptions failed")

            servers = self._horse_subs.servers_with_subscribers()
            if not servers:
                # no subscriptions: idle, do not watch random servers
                for name in list(self._horses.keys()):
                    self._horses.pop(name, None)
                await asyncio.sleep(max(10, int(cfg.get("poll_idle_seconds", 300) or 300)))
                continue

            active = set(servers)
            for name in list(self._horses.keys()):
                if name not in active:
                    self._horses.pop(name, None)

            pre_alert = int(cfg.get("pre_alert_minutes", 10) or 10)
            calibrate = int(cfg.get("calibrate_before_seconds", 30) or 30)
            idle_poll = int(cfg.get("poll_idle_seconds", 300) or 300)
            min_interval = max(3, idle_poll)

            async def _ensure_and_tick(server: str) -> int:
                safe = re.sub(r'[\\/:*?"<>|]', "_", server)
                state_path = os.path.join(self._data_dir, f"horse_{safe}.json")
                groups = self._horse_subs.groups_for_server(server)
                group_sig = tuple(self._sessions_from_groups(groups))
                watcher = self._horses.get(server)
                need_rebuild = (
                    watcher is None
                    or watcher.server != server
                    or getattr(watcher, "pre_alert_minutes", None) != pre_alert
                    or getattr(watcher, "calibrate_before_seconds", None) != calibrate
                    or getattr(watcher, "target_groups_sig", None) != group_sig
                    or getattr(watcher, "state_path", None) != state_path
                )
                if need_rebuild:
                    async def _send_for(text: str, _server=server) -> None:
                        live_groups = self._horse_subs.groups_for_server(_server)
                        await self._push_text_to(text, live_groups, server=_server)

                    watcher = HorseWatcher(
                        api=self.api,
                        state_path=state_path,
                        server=server,
                        pre_alert_minutes=pre_alert,
                        calibrate_before_seconds=calibrate,
                        send_fn=_send_for,
                    )
                    watcher.target_groups_sig = group_sig  # type: ignore[attr-defined]
                    self._horses[server] = watcher

                try:
                    await watcher.tick()
                except Exception:
                    logger.exception("horse tick failed server=%s", server)

                locked = bool(
                    watcher
                    and watcher.state.locked
                    and not watcher.state.pushed_refresh
                )
                interval = 5 if locked else idle_poll
                return max(3, interval)

            intervals = await asyncio.gather(*[_ensure_and_tick(s) for s in servers])
            for interval in intervals:
                min_interval = min(min_interval, int(interval))

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=min_interval)
            except asyncio.TimeoutError:
                pass
