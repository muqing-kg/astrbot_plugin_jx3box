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


def async_reports(rows):
    async def fetch(server, page_size=50):
        return list(rows)

    return fetch


def make_chitu(rid: int, created_at, map_name: str, minutes: int = 95) -> dict:
    return {
        "id": rid,
        "server": "梦江南",
        "type": "horse",
        "map_name": map_name,
        "content": f"当前马场内没有赤兔的马驹。\n距离下一匹赤兔出世还有{minutes}分钟\n",
        "created_at": created_at,
        "status": 0,
    }


def test_extract_chitu_prefers_future() -> None:
    """未来赤兔倒计时优先于已过去的旧记录，避免下一场被旧记录挡住。"""
    with tempfile.TemporaryDirectory() as td:
        w = HorseWatcher(api=DummyApi(), state_path=os.path.join(td, "h.json"), server="梦江南")
        now = now_cn()
        rows = [
            make_chitu(1, (now - timedelta(minutes=96)).isoformat(), "阴山大草原"),
            make_chitu(200, (now - timedelta(minutes=5)).isoformat(), "黑戈壁"),
        ]
        hit = w._extract_chitu(rows)
        assert hit is not None
        map_name, eta, minutes, event_id = hit
        assert map_name == "黑戈壁"
        assert event_id == "chitu:黑戈壁:2026-08-07T23:30:00+08:00" or event_id.startswith("chitu:黑戈壁:")
        assert eta > now


def test_chitu_countdown_lifecycle() -> None:
    """赤兔倒计时仍走发现/提前/刷新三连推。"""
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "h.json")
        now = now_cn()
        sent: list[str] = []

        async def send_fn(text):
            sent.append(text)

        reports = [
            {
                "id": 1,
                "content": "当前马场内没有赤兔的马驹。\n距离下一匹赤兔出世还有95分钟\n",
                "created_at": (now - timedelta(minutes=85)).isoformat(),
                "map_name": "阴山大草原",
            }
        ]
        api = SimpleNamespace(fetch_horse_reports=async_reports(reports))
        w = HorseWatcher(api=api, state_path=path, server="梦江南", send_fn=send_fn)

        asyncio.run(w.tick())
        assert w.state.pushed_found and "[赤兔速报]" in sent[0]

        asyncio.run(w.tick())
        assert w.state.pushed_pre and not w.state.pushed_refresh
        assert "分钟刷新" in sent[1]

        # 强制到点；校准窗口会再读 reports，故一并改掉源数据避免被覆盖
        past = now_cn() - timedelta(minutes=1)
        w.state.eta = past.isoformat()
        w.state.last_calibrated_at = past.isoformat()
        reports[:] = [
            make_chitu(1, (past - timedelta(minutes=95)).isoformat(), "阴山大草原")
        ]
        asyncio.run(w.tick())
        assert w.state.pushed_refresh
        assert "赤兔已刷新" in sent[-1]


def test_chitu_next_event_after_refresh() -> None:
    """赤兔刷新后不再每周静默，下一场倒计时出现时继续推。"""
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "h.json")
        now = now_cn()
        sent: list[str] = []

        async def send_fn(text):
            sent.append(text)

        reports = [
            make_chitu(1, (now - timedelta(minutes=96)).isoformat(), "阴山大草原")
        ]
        api = SimpleNamespace(fetch_horse_reports=async_reports(reports))
        w = HorseWatcher(api=api, state_path=path, server="梦江南", send_fn=send_fn)

        asyncio.run(w.tick())
        asyncio.run(w.tick())
        assert w.state.pushed_refresh and len(sent) == 2
        before = len(sent)
        asyncio.run(w.tick())
        assert len(sent) == before

        reports.append(
            make_chitu(2, now.isoformat(), "阴山大草原")
        )
        asyncio.run(w.tick())
        assert len(sent) == before + 1
        assert "[赤兔速报]" in sent[-1]
        assert not w.state.pushed_refresh


def test_upgrade_empty_event_id_no_repush() -> None:
    """旧状态缺 event_id 时，不能把同一场赤兔再推一次。"""
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "h.json")
        now = now_cn()
        sent: list[str] = []

        async def send_fn(text):
            sent.append(text)

        reports = [make_chitu(1, (now - timedelta(minutes=96)).isoformat(), "阴山大草原")]
        api = SimpleNamespace(fetch_horse_reports=async_reports(reports))
        w = HorseWatcher(api=api, state_path=path, server="梦江南", send_fn=send_fn)
        # 模拟升级前已推送刷新、但无 event_id 的磁盘状态
        eta = now - timedelta(minutes=1)
        w.state.cycle_id = w._cycle_id()
        w.state.locked = True
        w.state.pushed_found = True
        w.state.pushed_pre = True
        w.state.pushed_refresh = True
        w.state.map_name = "阴山大草原"
        w.state.eta = eta.isoformat()
        w.state.event_id = ""
        w._save()

        w2 = HorseWatcher(api=api, state_path=path, server="梦江南", send_fn=send_fn)
        asyncio.run(w2.tick())
        assert sent == []
        assert w2.state.event_id  # 已补齐
        assert w2.state.pushed_refresh is True


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



def test_fengyu_tip_rows() -> None:
    """风语颂歌: hang-pet trinket must not use equip/挂宠/精炼 0."""
    import json
    from astrbot_plugin_jx3box.item_tip import _build_rows, is_true_equip, _type_label
    from astrbot_plugin_jx3box.tip_html import select_tip_kind, build_tip_template_data
    from astrbot_plugin_jx3box.html_util import build_t2i_options
    from astrbot_plugin_jx3box.tip_html import TIP_RENDER_OPTIONS

    sample = ROOT / "data" / "samples" / "fengyu_songge.json"
    item = json.loads(sample.read_text(encoding="utf-8"))
    assert _type_label(item) == "挂宠"
    assert is_true_equip(item) is False
    assert select_tip_kind(item) == "mount_pet"
    rows = _build_rows(item)
    texts = [str(r.get("text") or "") for r in rows]
    kinds = [str(r.get("kind") or "") for r in rows]
    assert "挂宠" not in texts
    assert not any("精炼" in t for t in texts)
    assert "获取途径:" in texts
    assert "物品" in texts
    assert kinds.count("source_group") >= 1
    assert kinds.count("source_leaf") >= 2
    # leaves keep [] for item app
    assert any(t.startswith("[") and t.endswith("]") for t, k in zip(texts, kinds) if k == "source_leaf")
    data = build_tip_template_data(item)
    assert data["kind"] == "mount_pet"
    assert data["viewport_width"] <= 320
    # no fat svg arrow
    for r in data["rows"]:
        if r.get("kind") == "source_leaf":
            assert not r.get("icon_uri")
    opts = build_t2i_options(width=data["viewport_width"], base=TIP_RENDER_OPTIONS)
    assert opts["device_scale_factor"] == 2
    assert opts["omit_background"] is True


def test_strength_zero_hidden() -> None:
    from astrbot_plugin_jx3box.item_tip import _build_rows
    item = {"Name": "测试", "Quality": 1, "IsEquip": True, "MaxStrengthLevel": 0, "Source": "armor"}
    texts = [str(r.get("text") or "") for r in _build_rows(item)]
    assert not any("精炼" in t for t in texts)
    item2 = {"Name": "真装备", "Quality": 4, "IsEquip": True, "MaxStrengthLevel": 6, "Source": "armor", "attributes": [{"label": "攻击提高10", "color": "white"}]}
    texts2 = [str(r.get("text") or "") + "|" + str(r.get("right") or "") for r in _build_rows(item2)]
    assert any("精炼" in t for t in texts2)



def test_horse_attr_icon_rows() -> None:
    """Mount skill rows keep icon + green title + white body; no refine 0 spam."""
    import json
    from astrbot_plugin_jx3box.item_tip import _build_rows
    from astrbot_plugin_jx3box.tip_html import build_tip_template_data, select_tip_kind

    items = json.loads((ROOT / "data" / "samples" / "item_diverse_details_v2.json").read_text(encoding="utf-8"))
    item = next(it for it in items if str(it.get("id") or "") == "8_38705" or it.get("Name") == "谛听")
    rows = _build_rows(item)
    horse_rows = [r for r in rows if r.get("kind") == "horse_attr"]
    assert len(horse_rows) >= 2
    for hr in horse_rows:
        assert hr.get("icon_id")
        assert str(hr.get("icon_url") or "").startswith(("https://cdn.jx3box.com/icon/", "https://icon.jx3box.com/icon/"))
        assert hr.get("title")
        assert hr.get("body")
        assert str(hr.get("color")).upper() in {"#00D24B", "#00D24B"}
    texts = [str(r.get("text") or "") + "|" + str(r.get("right") or "") for r in rows]
    assert not any("精炼等级" in t and "0 / 0" in t for t in texts)
    assert not any(t.split("|", 1)[0].startswith("精饲") and r.get("kind") == "attr" for t, r in zip(texts, rows))

    data = build_tip_template_data(item)
    assert select_tip_kind(item) == "mount_pet"
    assert data["kind"] == "mount_pet"
    html_rows = [r for r in data["rows"] if r.get("kind") == "horse_attr"]
    assert len(html_rows) >= 2
    for hr in html_rows:
        assert ("cdn.jx3box.com/icon/" in str(hr.get("icon_uri") or "") or "icon.jx3box.com/icon/" in str(hr.get("icon_uri") or ""))
        assert hr.get("title")
        assert hr.get("body")




def test_tip_family_slot_gate() -> None:
    """Family schema gates slots; empty slots omitted; mount keeps horse icons."""
    import json
    from astrbot_plugin_jx3box.item_tip import _build_rows, tip_family_of, _slots_for_family

    items = json.loads((ROOT / "data" / "samples" / "item_diverse_details_v2.json").read_text(encoding="utf-8"))
    di = next(it for it in items if it.get("Name") == "谛听")
    assert tip_family_of(di) == "mount"
    allowed = _slots_for_family("mount")
    assert "horse_attr_icon" in allowed
    rows = _build_rows(di)
    slots = {r.get("slot") for r in rows if r.get("slot")}
    assert slots <= set(allowed) | {"title"}
    assert any(r.get("kind") == "horse_attr" for r in rows)
    assert not any(str(r.get("right") or "").startswith("精炼") and "0 / 0" in str(r.get("right") or "") for r in rows)

    fengyu = json.loads((ROOT / "data" / "samples" / "fengyu_songge.json").read_text(encoding="utf-8"))
    assert tip_family_of(fengyu) == "hang_pet"
    hang_allowed = _slots_for_family("hang_pet")
    assert "type_label" not in hang_allowed
    hang_rows = _build_rows(fengyu)
    hang_texts = [str(r.get("text") or "") for r in hang_rows]
    assert "挂宠" not in hang_texts
    assert not any(r.get("kind") == "horse_attr" for r in hang_rows)
    assert all((r.get("slot") in hang_allowed or r.get("slot") in {None, "title"} or r.get("kind") == "spacer") for r in hang_rows)




def test_quest_branch_and_reward_escape() -> None:
    """HTML quest card keeps branch data, deduplicates it, and escapes reward text."""
    import asyncio
    import json
    from astrbot_plugin_jx3box.quest_html import build_quest_template_data

    quests = json.loads((ROOT / "data" / "samples" / "quest_details_diverse.json").read_text(encoding="utf-8"))
    quest = next(q for q in quests if str(q.get("id")) == "31416")
    quest = dict(quest)
    quest["rewards"] = [
        {"type": "achievement", "name": "<b>测试成就</b>", "count": 1},
        {"type": "skill", "name": "<script>bad</script>", "count": 1},
        {"type": "custom<x>", "count": "<i>1</i>"},
    ]
    data = asyncio.run(build_quest_template_data(quest, item_meta={}, api=None))
    assert [b["name"] for b in data["branch_items"]] == ["候夜入营"]
    assert data["chain_items"]
    titles = [str(r.get("title") or "") for r in data["reward_cards"]]
    assert any("&lt;b&gt;" in title for title in titles)
    assert any("&lt;script&gt;" in title for title in titles)
    assert not any("<script>" in title for title in titles)


def test_quest_item_meta_concurrency() -> None:
    """Quest item metadata requests overlap instead of serializing."""
    import asyncio
    from astrbot_plugin_jx3box.quest_html import resolve_quest_item_meta

    class FakeApi:
        def __init__(self) -> None:
            self.active = 0
            self.max_active = 0

        async def get_item(self, iid):
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            await asyncio.sleep(0.01)
            self.active -= 1
            return {"Name": f"item-{iid}", "Quality": 2}

    api = FakeApi()
    quest = {"needItems": [{"id": str(i)} for i in range(1, 7)]}
    meta = asyncio.run(resolve_quest_item_meta(api, quest))
    assert len(meta) == 6
    assert api.max_active > 1
    assert api.max_active <= 4


def test_get_type_fallback_when_source_tree_gated(monkeypatch) -> None:
    """If family gates GetSource but allows GetType, source text still renders."""
    from astrbot_plugin_jx3box import item_tip

    monkeypatch.setattr(
        item_tip,
        "_FAMILY_SLOT_CACHE",
        {"equip_extended": frozenset({"title", "get_type"})},
    )

    item = {
        "Name": "扩展装备来源测试",
        "AucGenre": 26,
        "AucSubType": 1,
        "GetType": "活动",
        "GetSource": [{"label": "物品", "children": [{"label": "某物", "app": "item"}]}],
    }
    rows = item_tip._build_rows(item)
    texts = [str(r.get("text") or "") for r in rows]
    assert "物品来源：活动" in texts
    assert "获取途径:" not in texts


def test_get_type_fallback_when_source_tree_is_empty() -> None:
    """An empty GetSource payload must not hide a valid GetType line."""
    from astrbot_plugin_jx3box.item_tip import _build_rows

    item = {
        "Name": "空来源树测试",
        "AucGenre": 5,
        "GetType": "活动",
        "GetSource": [{}, {"label": "", "children": []}],
    }
    texts = [str(r.get("text") or "") for r in _build_rows(item)]
    assert "物品来源：活动" in texts
    assert "获取途径:" not in texts


def test_quest_dynamic_amounts_are_escaped() -> None:
    """Quest item/reward amounts are text, never executable HTML."""
    import asyncio
    from astrbot_plugin_jx3box.quest_html import build_quest_html

    quest = {
        "id": 1,
        "name": "数量转义测试",
        "needItems": [{"id": "1", "amount": '<img src=x onerror="bad()">'}],
        "rewards": [
            {"type": "train", "count": "<b>9</b>"},
            {"type": "item_group", "items": [{"id": "2", "amount": "<i>7</i>"}]},
        ],
    }
    html = asyncio.run(
        build_quest_html(
            quest,
            item_meta={"1": {"name": "目标"}, "2": {"name": "奖励"}},
        )
    )
    assert '<img src=x onerror="bad()">' not in html
    assert "<b>9</b>" not in html
    assert "<i>7</i>" not in html
    assert "&lt;img" in html
    assert "&lt;b&gt;9&lt;/b&gt;" in html
    assert "&lt;i&gt;7&lt;/i&gt;" in html


def test_quest_item_meta_does_not_guess_bare_id_prefix() -> None:
    """A bare quest item id must not accept an unrelated prefixed detail."""
    import asyncio
    from astrbot_plugin_jx3box.quest_html import resolve_quest_item_meta

    class FakeApi:
        async def get_item(self, iid):
            if str(iid) == "5_123":
                return {"Name": "错误候选", "Quality": 4}
            return None

        async def search_items(self, keyword, per=10):
            return []

    meta = asyncio.run(resolve_quest_item_meta(FakeApi(), {"needItems": [{"id": "123"}]}))
    assert meta["123"]["name"] == "123"


def test_schema_keeps_safe_source_slots_for_sparse_families() -> None:
    """Sparse samples must not permanently suppress ordinary source fields."""
    from astrbot_plugin_jx3box.item_tip import _slots_for_family

    for family in ("recipe", "book_read"):
        allowed = _slots_for_family(family)
        assert "get_source" in allowed
        assert "get_type" in allowed




def test_choice_list_layout_and_text() -> None:
    from astrbot_plugin_jx3box.choice_list import (
        choice_columns,
        column_major_indices,
        format_choice_text,
        choice_header,
        choice_footer,
        page_slice,
        total_pages,
    )

    assert choice_columns(11) == 1
    assert choice_columns(16) == 1
    assert choice_columns(17) == 2
    assert choice_columns(32) == 2
    assert choice_columns(33) == 3
    assert choice_columns(60) == 3
    assert choice_columns(61) == 4
    assert choice_columns(100) == 4

    assert total_pages(0) == 0
    assert total_pages(11) == 1
    assert total_pages(100) == 1
    assert total_pages(101) == 2
    assert total_pages(237) == 3

    rows = list(range(1, 238))
    page_rows, page, pages = page_slice(rows, 1)
    assert page == 1 and pages == 3 and page_rows == list(range(1, 101))
    page_rows, page, pages = page_slice(rows, 3)
    assert page == 3 and pages == 3 and page_rows == list(range(201, 238))
    page_rows, page, pages = page_slice(rows, 9)
    assert page == 3 and page_rows[-1] == 237

    cols = column_major_indices(10, 2)
    assert cols == [[0, 1, 2, 3, 4], [5, 6, 7, 8, 9]]
    cols4 = column_major_indices(100, 4)
    assert len(cols4) == 4
    assert cols4[0][0] == 0 and cols4[0][-1] == 24
    assert cols4[1][0] == 25 and cols4[3][-1] == 99

    text = format_choice_text(
        [{"Name": "甲"}, {"Name": "乙"}],
        kind_label="物品",
        name_key="Name",
    )
    assert "找到多个物品，请直接回复序号：" in text
    assert "1. 甲" in text and "2. 乙" in text
    assert "直接回复数字，例如：2" in text
    assert "更具体" not in text
    assert "/1" not in text

    assert choice_header(237, "物品", 1, 3) == "找到 237 个物品 · 第 1/3 页"
    assert "换页" in choice_footer(is_last=False)
    assert "已是最后一页" in choice_footer(is_last=True)
    assert "更具体" not in choice_footer(is_last=False)


def test_choice_image_render_basic(tmp_path) -> None:
    from astrbot_plugin_jx3box.choice_list import render_choice_list_image

    rows = [
        {"Name": f"物品{i}", "Quality": (i % 5) + 1, "IconID": 1000 + i}
        for i in range(1, 12)
    ]
    out = tmp_path / "choice11.png"
    path = render_choice_list_image(
        rows,
        kind="item",
        page=1,
        out_path=out,
        icon_bytes_map={},
    )
    assert Path(path).is_file()
    from PIL import Image
    img = Image.open(path)
    assert img.size[0] >= 400
    assert img.size[1] >= 200


def test_plugin_choice_paging_and_digit_select() -> None:
    """Plugin keeps full rows, pages by 100, accepts bare digits and 换页."""
    import asyncio
    from types import SimpleNamespace

    with tempfile.TemporaryDirectory() as td:
        plugin = make_plugin(td)
        rows = [{"Name": f"N{i}", "id": str(i), "Quality": 2, "IconID": i} for i in range(1, 112)]
        ev = SimpleNamespace(
            message_str="",
            unified_msg_origin="aiocqhttp:GroupMessage:100",
            get_platform_name=lambda: "aiocqhttp",
            get_group_id=lambda: "100",
            get_sender_id=lambda: "u1",
            stop_event=lambda: None,
            plain_result=lambda t: t,
            chain_result=lambda c: c,
            image_result=None,
        )
        # save full list
        plugin._save_choices(ev, "item", rows)
        cache = next(iter(plugin._choice_cache.values()))
        assert len(cache["rows"]) == 111
        assert cache.get("page", 1) == 1

        # digit beyond old /10 limit
        ev.message_str = "42"
        outs = []
        async def _run_choose():
            async for x in plugin.cmd_choose(ev):
                outs.append(x)
        # monkeypatch detail sender to avoid network
        async def fake_item(event, row):
            yield f"DETAIL:{row.get('id')}"
        plugin._send_item_detail = fake_item
        asyncio.run(_run_choose())
        assert outs and str(outs[0]).startswith("DETAIL:42")
        assert plugin._choice_cache == {}

        # restore and test 换页 last page message
        plugin._save_choices(ev, "item", rows)
        # force page 2 of 2
        for k in list(plugin._choice_cache):
            plugin._choice_cache[k]["page"] = 2
        ev.message_str = "换页"
        outs2 = []
        async def _run_page():
            async for x in plugin.cmd_choose(ev):
                outs2.append(x)
        asyncio.run(_run_page())
        assert outs2 and "已经是最后一页" in str(outs2[0])


if __name__ == "__main__":
    test_server_match()
    test_subscribe_and_isolation()
    test_admin_list_delete()
    test_push_uses_subscription_only()
    test_format_has_server()
    test_schema_has_no_server_fields()
    test_cycle_resets_without_refresh()
    test_extract_chitu_prefers_future()
    test_chitu_countdown_lifecycle()
    test_chitu_next_event_after_refresh()
    test_upgrade_empty_event_id_no_repush()
    test_sanitize_color()
    test_choice_prefers_user_key()
    test_t2i_options_and_crop()
    test_fengyu_tip_rows()
    test_strength_zero_hidden()
    test_horse_attr_icon_rows()
    test_tip_family_slot_gate()
    test_quest_branch_and_reward_escape()
    test_quest_item_meta_concurrency()
    test_get_type_fallback_when_source_tree_gated()
    test_get_type_fallback_when_source_tree_is_empty()
    test_quest_dynamic_amounts_are_escaped()
    test_quest_item_meta_does_not_guess_bare_id_prefix()
    test_schema_keeps_safe_source_slots_for_sparse_families()
    test_choice_list_layout_and_text()
    test_plugin_choice_paging_and_digit_select()
    print("HORSE_COMMAND_SUB_OK")
