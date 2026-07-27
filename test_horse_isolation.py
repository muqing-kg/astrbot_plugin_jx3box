"""Command-subscription isolation tests (no AstrBot runtime)."""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import types
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

# stubs
astrbot = types.ModuleType("astrbot")
astrbot_api = types.ModuleType("astrbot.api")
astrbot_api_event = types.ModuleType("astrbot.api.event")
astrbot_api_star = types.ModuleType("astrbot.api.star")
astrbot_api_msg = types.ModuleType("astrbot.api.message_components")


class AstrBotConfig(dict):
    pass


class AstrMessageEvent:
    pass


class MessageChain:
    def __init__(self, chain=None):
        self.chain = chain or []


def _identity_deco(*args, **kwargs):
    def deco(fn):
        return fn
    if args and callable(args[0]) and len(args) == 1 and not kwargs:
        return args[0]
    return deco


class _EventMessageType:
    ALL = "ALL"


class _PermissionType:
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"


class _Filter:
    EventMessageType = _EventMessageType
    PermissionType = _PermissionType

    def command(self, *args, **kwargs):
        return _identity_deco

    def event_message_type(self, *args, **kwargs):
        return _identity_deco

    def permission_type(self, *args, **kwargs):
        return _identity_deco


class Context:
    pass


class Star:
    def __init__(self, context=None):
        self.context = context


class StarTools:
    @staticmethod
    def get_data_dir(name: str):
        return ROOT / "data"


def register(*args, **kwargs):
    def deco(cls):
        return cls
    return deco


class Plain:
    def __init__(self, text: str):
        self.text = text


astrbot_api.AstrBotConfig = AstrBotConfig
astrbot_api.logger = SimpleNamespace(
    info=lambda *a, **k: None,
    warning=lambda *a, **k: None,
    exception=lambda *a, **k: None,
)
astrbot_api_event.AstrMessageEvent = AstrMessageEvent
astrbot_api_event.MessageChain = MessageChain
astrbot_api_event.filter = _Filter()
astrbot_api_star.Context = Context
astrbot_api_star.Star = Star
astrbot_api_star.StarTools = StarTools
astrbot_api_star.register = register
astrbot_api_msg.Plain = Plain
sys.modules["astrbot"] = astrbot
sys.modules["astrbot.api"] = astrbot_api
sys.modules["astrbot.api.event"] = astrbot_api_event
sys.modules["astrbot.api.star"] = astrbot_api_star
sys.modules["astrbot.api.message_components"] = astrbot_api_msg

from astrbot_plugin_jx3box.horse_subscribe import HorseSubscriptionStore
from astrbot_plugin_jx3box.horse_watcher import HorseWatcher, now_cn
from astrbot_plugin_jx3box.main import Jx3BoxPlugin


class DummyApi:
    async def fetch_horse_reports(self, server: str, page_size: int = 50):
        return []


def make_store(td: str) -> HorseSubscriptionStore:
    return HorseSubscriptionStore(
        path=os.path.join(td, "horse_subscriptions.json"),
        bundled_server_list=str((ROOT / "assets" / "server_list.json").resolve()),
    )


def make_plugin(td: str) -> Jx3BoxPlugin:
    plugin = object.__new__(Jx3BoxPlugin)
    plugin.config = {"enabled": True, "horse": {"enabled": True, "pre_alert_minutes": 10, "poll_idle_seconds": 300, "calibrate_before_seconds": 30}}
    plugin.context = SimpleNamespace(send_message=None)
    plugin.api = DummyApi()
    plugin._data_dir = td
    plugin._horses = {}
    plugin._choice_cache = {}
    plugin._stop = asyncio.Event()
    plugin._horse_subs = make_store(td)
    return plugin


def test_server_match() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = make_store(td)
        assert store.match_server("梦江南") == "梦江南"
        assert store.match_server(" 梦江南 ") == "梦江南"
        assert store.match_server("火星一号") is None


def test_subscribe_and_isolation() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = make_store(td)
        ok, msg, row = store.subscribe(
            server="梦江南",
            group_id="111",
            session="aiocqhttp:GroupMessage:111",
            platform="aiocqhttp",
        )
        assert ok and row and "订阅成功" in msg
        ok2, msg2, _ = store.subscribe(
            server="乱写",
            group_id="111",
            session="aiocqhttp:GroupMessage:111",
        )
        assert (not ok2) and msg2 == "请输入正确区服！"
        store.subscribe(
            server="乾坤一掷",
            group_id="111",
            session="aiocqhttp:GroupMessage:111",
        )
        store.subscribe(
            server="乾坤一掷",
            group_id="222",
            session="aiocqhttp:GroupMessage:222",
        )
        assert store.groups_for_server("梦江南") == ["aiocqhttp:GroupMessage:111"]
        assert set(store.groups_for_server("乾坤一掷")) == {
            "aiocqhttp:GroupMessage:111",
            "aiocqhttp:GroupMessage:222",
        }
        # 222 must not get 梦江南
        assert "aiocqhttp:GroupMessage:222" not in store.groups_for_server("梦江南")


def test_admin_list_delete() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = make_store(td)
        store.subscribe(server="梦江南", group_id="111", session="aiocqhttp:GroupMessage:111")
        store.subscribe(server="乾坤一掷", group_id="222", session="aiocqhttp:GroupMessage:222")
        rows = store.list_all()
        assert len(rows) == 2
        ok, msg, row = store.unsubscribe_index(1)
        assert ok and row is not None
        assert len(store.list_all()) == 1


def test_push_uses_subscription_only() -> None:
    with tempfile.TemporaryDirectory() as td:
        plugin = make_plugin(td)
        plugin._horse_subs.subscribe(
            server="梦江南", group_id="111", session="aiocqhttp:GroupMessage:111"
        )
        plugin._horse_subs.subscribe(
            server="乾坤一掷", group_id="222", session="aiocqhttp:GroupMessage:222"
        )
        sent: list[tuple[str, str]] = []

        async def send_message(session, chain):
            sent.append((session, chain.chain[0].text))

        plugin.context = SimpleNamespace(send_message=send_message)

        async def run():
            # emulate send-time resolve
            groups = plugin._horse_subs.groups_for_server("梦江南")
            await plugin._push_text_to("ONLY 梦江南", groups, server="梦江南")
            groups_b = plugin._horse_subs.groups_for_server("乾坤一掷")
            await plugin._push_text_to("ONLY 乾坤一掷", groups_b, server="乾坤一掷")

        asyncio.run(run())
        by = {}
        for s, text in sent:
            by.setdefault(s, []).append(text)
        assert by["aiocqhttp:GroupMessage:111"] == ["ONLY 梦江南"]
        assert by["aiocqhttp:GroupMessage:222"] == ["ONLY 乾坤一掷"]


def test_format_has_server() -> None:
    with tempfile.TemporaryDirectory() as td:
        w = HorseWatcher(api=DummyApi(), state_path=os.path.join(td, "h.json"), server="飞龙在天")
        eta = now_cn() + timedelta(minutes=12)
        for text in (w._format_found(eta, "昆仑"), w._format_pre(eta, "昆仑"), w._format_refresh("昆仑")):
            assert "区服：飞龙在天" in text


def test_schema_has_no_server_fields() -> None:
    import json
    schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8-sig"))
    items = schema["horse"]["items"]
    assert "server" not in items
    assert "servers" not in items
    assert "target_groups" not in items
    assert "enabled" in items




def test_cycle_resets_without_refresh() -> None:
    """cycle_id change must reset even if pushed_refresh is False."""
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "h.json")
        w = HorseWatcher(api=DummyApi(), state_path=path, server="飞龙在天")
        w.state.cycle_id = "20000101"
        w.state.locked = True
        w.state.pushed_found = True
        w.state.pushed_refresh = False
        w.state.map_name = "旧地图"
        w._save()

        async def run():
            await w.tick()

        asyncio.run(run())
        assert w.state.cycle_id != "20000101"
        assert w.state.locked is False
        assert w.state.pushed_found is False
        assert w.state.map_name == ""


def test_sanitize_color() -> None:
    from astrbot_plugin_jx3box.html_util import sanitize_css_color
    assert sanitize_css_color("#ff00aa") == "#ff00aa"
    assert sanitize_css_color("red;background:url(x)") == "#FFFFFF"
    assert sanitize_css_color("rgb(1,2,3)") == "rgb(1,2,3)"


def test_choice_prefers_user_key() -> None:
    with tempfile.TemporaryDirectory() as td:
        plugin = make_plugin(td)
        ev = SimpleNamespace(
            unified_msg_origin="aiocqhttp:GroupMessage:9",
            get_group_id=lambda: "9",
            get_platform_name=lambda: "aiocqhttp",
            get_sender_id=lambda: "u1",
            message_str="",
        )
        plugin._save_choices(ev, "item", [{"Name": "A", "id": "1"}])
        keys = list(plugin._choice_cache.keys())
        assert any(":user:u1" in k for k in keys)
        assert not any(k == "group:9" for k in keys)




def test_t2i_options_and_crop() -> None:
    from astrbot_plugin_jx3box.html_util import build_t2i_options, content_width_for_kind, crop_render_whitespace
    from astrbot_plugin_jx3box.tip_html import build_tip_template_data, TIP_RENDER_OPTIONS
    from astrbot_plugin_jx3box.quest_html import QUEST_RENDER_OPTIONS
    from PIL import Image

    assert content_width_for_kind("equip") == 341
    assert content_width_for_kind("quest", quest=True) == 860
    data = build_tip_template_data({"Name": "测试", "Quality": 5, "Desc": 'text="短" font=100'})
    assert data["viewport_width"] <= 320
    opts = build_t2i_options(width=data["viewport_width"], base=TIP_RENDER_OPTIONS)
    assert opts["omit_background"] is True
    assert opts["viewport_width"] == data["viewport_width"]
    assert opts["viewport"]["width"] == data["viewport_width"]
    assert QUEST_RENDER_OPTIONS.get("omit_background") is True

    # simulate oversized t2i canvas with tip panel in top-left
    img = Image.new("RGBA", (800, 600), (255, 255, 255, 255))
    for y in range(20, 160):
        for x in range(10, 200):
            img.putpixel((x, y), (15, 34, 34, 255))
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "wide.png"
        img.save(path)
        out = crop_render_whitespace(path, dark_panel=True, pad=0)
        cropped = Image.open(out)
        assert cropped.size[0] < 250
        assert cropped.size[1] < 200
        c = cropped.getpixel((0, 0))
        assert c[0] < 40 and c[1] < 50

if __name__ == "__main__":
    test_server_match()
    test_subscribe_and_isolation()
    test_admin_list_delete()
    test_push_uses_subscription_only()
    test_format_has_server()
    test_schema_has_no_server_fields()
    test_cycle_resets_without_refresh()
    test_sanitize_color()
    test_choice_prefers_user_key()
    test_t2i_options_and_crop()
    print("HORSE_COMMAND_SUB_OK")
