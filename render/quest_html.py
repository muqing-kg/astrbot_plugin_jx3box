# -*- coding: utf-8 -*-
"""Quest detail HTML multi-template for AstrBot html_render / astrbot-t2i."""
from __future__ import annotations

import asyncio
import base64
import html as html_lib
import io
import re
from pathlib import Path
from typing import Any

from .html_util import build_t2i_options, content_width_for_kind, crop_render_whitespace, is_http_url, sanitize_css_color
from .item_tip import QUALITY_COLORS
from .renderers import (
    _QUEST_TYPE_LABELS,
    _format_rewards,
    parse_tag_to_plain,
    parse_tags,
)

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
_TEMPLATE_DIR = _PLUGIN_DIR / "assets" / "quest_templates"
_BASE_CSS = _TEMPLATE_DIR / "base.css"

# Light-theme tag colors closer to jx3box quest page
_LIGHT_TAG_COLORS = {
    "G": "#000000",      # 段落正文
    "F171": "#d97706",   # 物品链接
    "F172": "#dc2626",
    "F173": "#6C967E",   # NPC/地点链接（灰绿）
    "F174": "#8F9790",   # 叙述/旁白（灰）
    "N": "#000000",      # 玩家名（黑）
    "DEFAULT": "#000000",
}

QUEST_RENDER_OPTIONS: dict[str, Any] = {
    "full_page": True,
    "type": "png",
    "omit_background": True,
    "animations": "disabled",
    "caret": "hide",
    "scale": "device",
}

QUEST_CARD_TMPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width={{ viewport_width }}, initial-scale=1"/>
<style>{{ css | safe }}</style>
</head>
<body>
<div id="quest-root">
  <div class="q-head">
    <span class="q-title{% if title_dark %} dark{% endif %}">{{ name_main }}</span>{% if name_suffix %}<span class="q-suffix">{{ name_suffix }}</span>{% endif %}
    <span class="q-id">(ID:{{ qid }})</span>
  </div>

  {% if can_share %}
  <div class="q-share">
    <svg viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg"><rect x="3" y="2.5" width="14" height="15.5" rx="2" fill="#e8e2d0" stroke="#988060"/><rect x="6.5" y="1" width="7" height="3" rx="1" fill="#988060"/><path d="M6 8.5h8M6 11.5h8M6 14.5h5" stroke="#b0a080" stroke-width="1.4" fill="none"/></svg>
    <span class="txt">可分享任务</span>
  </div>
  {% endif %}

  {% if start_line.where or end_line.where %}
  <div class="q-nodes">
    {% if start_line.where %}<div class="q-node"><span class="label">任务起点:</span> <span class="where">{{ start_line.where }}</span>{% if start_line.icon_uri %}<img class="icon" src="{{ start_line.icon_uri }}" alt=""/>{% endif %}{% if start_line.nid %}<span class="nid">（{{ start_line.id_label }}：{{ start_line.nid }}）</span>{% endif %}</div>{% endif %}
    {% if end_line.where %}<div class="q-node"><span class="label">任务终点:</span> <span class="where">{{ end_line.where }}</span>{% if end_line.nid %}<span class="nid">（{{ end_line.id_label }}：{{ end_line.nid }}）</span>{% endif %}</div>{% endif %}
  </div>
  <div class="q-rule-dashed"></div>
  {% endif %}

  {% if objective_html or need_items or kill_npcs %}
  <div class="q-section">
    <div class="q-section-title"><span class="tri"></span>任务目标</div>
    <div class="q-rule-dotted"></div>
    {% if objective_html %}<div class="q-body">{{ objective_html | safe }}</div>{% endif %}
    {% for v in quest_values %}
    <div class="q-sub">{{ v.name }} × {{ v.amount }}</div>
    {% endfor %}
    {% for k in kill_npcs %}
    <div class="q-sub">击杀 <b>{{ k.name }}</b> × {{ k.amount }}</div>
    {% endfor %}
    {% for it in need_items %}
    <div class="q-collect">
      <span class="act">收集</span>
      {% if it.icon_uri %}<img class="cicon" src="{{ it.icon_uri }}" alt=""/>{% endif %}
      <span class="iname">{{ it.name }}</span>
      <span class="amt">× {{ it.amount }}</span>
    </div>
    {% endfor %}
  </div>
  {% endif %}

  {% if description_html %}
  <div class="q-section">
    <div class="q-section-title"><span class="tri"></span>任务描述</div>
    <div class="q-rule-dotted"></div>
    <div class="q-body">{{ description_html | safe }}</div>
  </div>
  {% endif %}

  {% if offer_items %}
  <div class="q-section">
    <div class="q-section-title"><span class="tri"></span>提供物品</div>
    <div class="q-rule-dotted"></div>
    <div class="q-offer">
      {% for it in offer_items %}{% if it.icon_uri %}<img class="oicon" src="{{ it.icon_uri }}" alt=""/>{% endif %}{% endfor %}
    </div>
  </div>
  {% endif %}

  {% if reward_cards %}
  <div class="q-section">
    <div class="q-section-title"><span class="tri"></span>任务奖励</div>
    <div class="q-rule-dotted"></div>
    {% for r in reward_cards if (not r.is_card) and r.kind == "item_group_tip" %}
    <div class="q-sub group-tip">{{ r.title }}</div>
    {% endfor %}
    <div class="q-rewards">
      {% for r in reward_cards if r.is_card %}
      <div class="q-reward">
        {% if r.icon_uri %}<img class="ricon" src="{{ r.icon_uri }}" alt=""/>{% endif %}
        <div class="rtext">
          <div class="rname{% if r.is_item %} item{% endif %}">{{ r.title }}</div>
          {% if r.amount %}<div class="ramt">{{ r.amount }}</div>{% endif %}
        </div>
      </div>
      {% endfor %}
    </div>
    {% for r in reward_cards if (not r.is_card) and r.kind not in ["item_group_tip"] %}
    <div class="q-sub">{% if r.html %}{{ r.html | safe }}{% else %}{{ r.title }}{% endif %}</div>
    {% endfor %}
  </div>
  {% endif %}

  {% if chain_items %}
  <div class="q-chain-sep"><span>⛓ 任务链</span></div>
  <div class="q-chain">
    {% for c in chain_items %}
      {% if not loop.first %}<span class="chain-sep">》</span>{% endif %}
      <span class="chain-item{% if c.current %} current{% endif %}">[{{ c.name }}]</span>
    {% endfor %}
  </div>
  {% endif %}
</div>
</body>
</html>"""


def _escape(text: Any) -> str:
    return html_lib.escape(str(text or ""), quote=True)


def _load_css() -> str:
    if _BASE_CSS.is_file():
        return _BASE_CSS.read_text(encoding="utf-8")
    return ""


def _npc_parts(node: Any) -> dict[str, str]:
    if not isinstance(node, dict):
        return {"where": "", "nid": ""}
    map_name = str(node.get("mapName") or "").strip()
    name = str(node.get("name") or "").strip()
    where = " - ".join([x for x in [map_name, name] if x])
    nid = node.get("id")
    return {"where": where, "nid": "" if nid in (None, "") else str(nid)}


def _segments_to_html(raw: Any) -> str:
    segs = parse_tags(raw if isinstance(raw, str) else str(raw or ""))
    if not segs:
        plain = parse_tag_to_plain(raw if isinstance(raw, str) else str(raw or ""))
        if not plain:
            return ""
        parts = []
        for para in plain.split("\n"):
            if para.strip():
                parts.append(f"<p>{_escape(para)}</p>")
        return "".join(parts)

    html_parts: list[str] = []
    buf: list[str] = []

    def _flush() -> None:
        para = "".join(buf).strip()
        if para:
            html_parts.append(f"<p>{para}</p>")
        elif html_parts:
            html_parts.append("<p><br/></p>")
        buf.clear()

    injected_n = False
    for text, color in segs:
        if text == "\n":
            _flush()
            injected_n = False
            continue
        # <N> 为玩家名占位：站点渲染为「侠士」前缀（每段一次）
        if color == "#F6D36A" and not injected_n and text.startswith(("，", ",")):
            text = "侠士" + text
            injected_n = True
        c = color
        if color in {"#D7DCE5", "#7FDBA8", "#FFD76A", "#FF7A6B", "#6EC8FF", "#B7F0B0", "#F6D36A"}:
            rev = {
                "#7FDBA8": _LIGHT_TAG_COLORS["G"],
                "#FFD76A": _LIGHT_TAG_COLORS["F171"],
                "#FF7A6B": _LIGHT_TAG_COLORS["F172"],
                "#6EC8FF": _LIGHT_TAG_COLORS["F173"],
                "#B7F0B0": _LIGHT_TAG_COLORS["F174"],
                "#F6D36A": _LIGHT_TAG_COLORS["N"],
                "#D7DCE5": _LIGHT_TAG_COLORS["DEFAULT"],
            }
            c = rev.get(color, _LIGHT_TAG_COLORS["DEFAULT"])
        elif color == _LIGHT_TAG_COLORS.get("DEFAULT") or not color:
            c = _LIGHT_TAG_COLORS["DEFAULT"]
        c = sanitize_css_color(c, _LIGHT_TAG_COLORS["DEFAULT"])
        pieces = str(text).split("\n")
        for i, piece in enumerate(pieces):
            if i > 0:
                _flush()
                injected_n = False
            if piece:
                buf.append(f'<span style="color:{c}">{_escape(piece)}</span>')
    _flush()
    return "".join(html_parts)


def _quality_color(q: Any) -> str:
    """Quality color for quest light theme.

    Official tip dark panel uses pure white for q1; on white quest cards
    pure white is invisible, so map q1 to dark text.
    """
    try:
        qi = int(q)
    except Exception:
        qi = 1
    if qi <= 1:
        return "#2B2F36"
    return QUALITY_COLORS.get(qi, "#2563eb")


def _icon_data_uri(icon_bytes: bytes | None) -> str:
    if not icon_bytes:
        return ""
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(icon_bytes)).convert("RGBA")
        im = im.resize((28, 28), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception:
        b64 = base64.b64encode(icon_bytes).decode("ascii")
        return f"data:image/png;base64,{b64}"



async def _fetch_icon_data_uri(icon_id: Any, api: Any | None = None) -> str:
    """Load icon via async HttpClient/Jx3Api when possible."""
    if icon_id in (None, ""):
        return ""
    try:
        iid = int(icon_id)
    except Exception:
        return ""
    try:
        if api is not None and hasattr(api, "get_icon_bytes"):
            raw = await api.get_icon_bytes(iid)
            return _icon_data_uri(raw)
        if api is not None and getattr(api, "http", None) is not None:
            raw = await api.http.get_bytes(f"https://icon.jx3box.com/icon/{iid}.png")
            return _icon_data_uri(raw)
    except Exception:
        return ""
    return ""


def collect_quest_item_ids(quest: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for key in ("needItems", "offerItems"):
        for it in quest.get(key) or []:
            if isinstance(it, dict) and it.get("id") not in (None, ""):
                ids.append(str(it.get("id")))
    for r in quest.get("rewards") or []:
        if not isinstance(r, dict):
            continue
        typ = str(r.get("type") or "")
        if typ == "item_group":
            for it in r.get("items") or []:
                if isinstance(it, dict) and it.get("id") not in (None, ""):
                    ids.append(str(it.get("id")))
    seen: set[str] = set()
    out: list[str] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


async def resolve_quest_item_meta(api: Any, quest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Fetch name/quality/icon for quest-related item ids.

    Runtime CDN pull via icon.jx3box.com when IconID exists.
    Falls back to alternate id forms / keyword search when direct get_item misses.
    """
    meta: dict[str, dict[str, Any]] = {}

    async def _load_one(iid: str) -> dict[str, Any]:
        detail = None
        # direct
        try:
            detail = await api.get_item(iid)
        except Exception:
            detail = None
        # search fallback
        if not detail and hasattr(api, "search_items"):
            try:
                rows = await api.search_items(str(iid), per=10)
            except Exception:
                rows = []
            for row in rows or []:
                rid = str(row.get("id") or "")
                if rid == iid or rid.endswith("_" + iid.split("_")[-1]):
                    try:
                        detail = await api.get_item(rid)
                    except Exception:
                        detail = row
                    if detail:
                        break
            if not detail and rows:
                # last resort first row
                try:
                    detail = await api.get_item(rows[0].get("id"))
                except Exception:
                    detail = rows[0]

        name = ""
        quality = 1
        icon_uri = ""
        if isinstance(detail, dict):
            name = str(detail.get("Name") or detail.get("name") or "")
            try:
                quality = int(detail.get("Quality") or 1)
            except Exception:
                quality = 1
            icon_id = detail.get("IconID")
            if icon_id is not None and hasattr(api, "get_icon_bytes"):
                try:
                    icon_bytes = await api.get_icon_bytes(icon_id)
                    icon_uri = _icon_data_uri(icon_bytes)
                except Exception:
                    icon_uri = ""
        if not name:
            name = iid
        return {
            "name": name,
            "quality": quality,
            "color": _quality_color(quality),
            "icon_uri": icon_uri,
        }

    item_ids = [str(iid) for iid in collect_quest_item_ids(quest)]
    if not item_ids:
        return meta

    # Bound fan-out so complex reward lists do not serialize, while keeping API load modest.
    semaphore = asyncio.Semaphore(4)

    async def _load_limited(iid: str) -> tuple[str, dict[str, Any]]:
        async with semaphore:
            return iid, await _load_one(iid)

    pairs = await asyncio.gather(*(_load_limited(iid) for iid in item_ids))
    meta.update(pairs)
    return meta


def _item_rows(raw_list: Any, item_meta: dict[str, dict[str, Any]] | None) -> list[dict[str, Any]]:
    item_meta = item_meta or {}
    rows: list[dict[str, Any]] = []
    for it in raw_list or []:
        if not isinstance(it, dict):
            continue
        iid = str(it.get("id") or "")
        if not iid:
            continue
        amount = _escape(it.get("amount", 1))
        m = item_meta.get(iid) or {}
        rows.append(
            {
                "id": iid,
                "name": _escape(m.get("name") or iid),
                "amount": amount,
                "color": "#909090",
                "icon_uri": m.get("icon_uri") or "",
            }
        )
    return rows





def _file_data_uri(path: Path) -> str:
    if not path.is_file():
        return ""
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _reward_icon_data_uri(kind: str) -> str:
    # composed cards: train/tongFund/... ; fallback single fblist
    path = _TEMPLATE_DIR / "icons" / f"{kind}.png"
    return _file_data_uri(path)


def _price_icon_uri(unit: str) -> str:
    return _file_data_uri(_TEMPLATE_DIR / "price" / f"{unit}.png")


def _money_html(count: Any) -> str:
    try:
        n = int(count or 0)
    except Exception:
        return _escape(count)
    if n < 0:
        n = 0
    gold, rem = divmod(n, 10000)
    silver, copper = divmod(rem, 100)
    parts = []
    for val, unit, alt in ((gold, "jin", "金"), (silver, "yin", "银"), (copper, "tong", "铜")):
        icon = _price_icon_uri(unit)
        if icon:
            parts.append(
                f'<span class="price-part"><span class="price-val">{val}</span>'
                f'<img class="price-icon" src="{icon}" alt="{alt}"/></span>'
            )
        else:
            parts.append(f"<span>{val}{alt}</span>")
    return "获得金钱：" + "".join(parts)



async def _format_reward_cards(
    rewards: list[dict[str, Any]] | None,
    api: Any | None = None,
) -> list[dict[str, Any]]:
    """Official wiki reward cards.

    point-reward.vue mapping:
      train->17, tongFund->30, prestige->33, titlePoint->37, vigor->80,
      justice->34, tongResource->36, bg frame->18
    money -> GamePrice icons
    exp/affect -> text lines
    item_group -> item cards with CDN icons (filled later via item_meta)
    achievement/skill -> icon id from reward payload
    """
    if not rewards:
        return []

    point_types = {
        "train": "修为",
        "tongFund": "帮会资金",
        "prestige": "名剑币",
        "titlePoint": "战阶积分",
        "vigor": "精力",
        "justice": "侠义点",
        "tongResource": "阵营资源",
    }

    cards: list[dict[str, Any]] = []
    extras: list[dict[str, Any]] = []

    for r in rewards:
        if not isinstance(r, dict):
            continue
        typ = str(r.get("type") or "").strip()
        c = r.get("count", 0)

        if typ in point_types:
            cards.append({
                "kind": typ,
                "title": point_types[typ],
                "amount": _escape(f"× {c}"),
                "icon_uri": _reward_icon_data_uri(typ),
                "is_card": True,
                "is_item": False,
                "html": "",
                "item_id": "",
            })
            continue

        if typ == "exp":
            extras.append({
                "kind": "exp",
                "title": _escape(f"获得阅历：{c}"),
                "amount": "",
                "icon_uri": "",
                "is_card": False,
                "html": "",
                "item_id": "",
            })
            continue

        if typ == "money":
            extras.append({
                "kind": "money",
                "title": "",
                "amount": "",
                "icon_uri": "",
                "is_card": False,
                "html": _money_html(c),
                "item_id": "",
            })
            continue

        if typ == "affect":
            force = str(r.get("force") or "声望")
            try:
                n = int(c or 0)
            except Exception:
                n = 0
            sign = "+" if n > 0 else ""
            extras.append({
                "kind": "affect",
                "title": _escape(f"获得声望（{force}）{sign}{n}"),
                "amount": "",
                "icon_uri": "",
                "is_card": False,
                "html": "",
                "item_id": "",
            })
            continue

        if typ == "achievement":
            name = str(r.get("name") or "成就")
            icon = r.get("icon")
            icon_uri = ""
            if icon not in (None, ""):
                icon_uri = await _fetch_icon_data_uri(icon, api)
            cards.append({
                "kind": "achievement",
                "title": _escape(name),
                "amount": "",
                "icon_uri": icon_uri or _reward_icon_data_uri("train"),
                "is_card": True,
                "html": "",
                "item_id": str(r.get("id") or ""),
            })
            continue

        if typ == "skill":
            name = str(r.get("name") or "技能")
            icon = r.get("icon")
            icon_uri = ""
            if icon not in (None, ""):
                icon_uri = await _fetch_icon_data_uri(icon, api)
            cards.append({
                "kind": "skill",
                "title": _escape(name),
                "amount": "",
                "icon_uri": icon_uri,
                "is_card": True,
                "html": "",
                "item_id": str(r.get("id") or ""),
            })
            continue

        if typ == "item_group":
            items = r.get("items") or []
            if r.get("all"):
                tip = "你将获得以下全部道具" + ("（按门派）" if r.get("bySchool") else "") + "："
            else:
                tip = "你可以从以下道具中选择一项："
            extras.append({
                "kind": "item_group_tip",
                "title": tip,
                "amount": "",
                "icon_uri": "",
                "is_card": False,
                "html": "",
                "item_id": "",
            })
            for it in items:
                if not isinstance(it, dict):
                    continue
                iid = str(it.get("id") or "").strip()
                if not iid:
                    continue
                raw_amt = str(it.get("amount", 1))
                amount = "" if raw_amt == "1" else f"× {raw_amt}"
                cards.append({
                    "kind": "item",
                    "title": iid,  # replaced later with real name
                    "amount": amount,
                    "icon_uri": "",
                    "is_card": True,
                    "is_item": True,
                    "html": "",
                    "item_id": iid,
                })
            continue

        if typ:
            extras.append({
                "kind": typ,
                "title": _escape(f"{typ} {c}"),
                "amount": "",
                "icon_uri": "",
                "is_card": False,
                "html": "",
                "item_id": "",
            })

    return cards + extras


async def build_quest_template_data(
    quest: dict[str, Any],
    item_meta: dict[str, dict[str, Any]] | None = None,
    api: Any | None = None,
) -> dict[str, Any]:
    desc = quest.get("desc") or {}
    if not isinstance(desc, dict):
        desc = {}

    qid = quest.get("id") or desc.get("QuestID") or ""
    name = str(quest.get("name") or desc.get("QuestName") or "未知任务")

    start_line = _npc_parts(quest.get("start") or {})
    end_line = _npc_parts(quest.get("end") or {})
    start_node = quest.get("start") if isinstance(quest.get("start"), dict) else {}
    if start_node.get("type") == "item":
        # 物品起点：地图名保留，NPCID 改为物品ID，并尝试带图标
        item_id = str(start_node.get("id") or "")
        start_line["where"] = f"{start_node.get('mapName') or ''} - ".replace(" -  - ", " - ")
        start_line["nid"] = item_id
        start_line["id_label"] = "物品ID"
        icon_uri = ""
        if api is not None and item_id:
            try:
                detail = await api.get_item(item_id)
                icon_id = (detail or {}).get("IconID")
                if icon_id is not None:
                    icon_uri = await _fetch_icon_data_uri(icon_id, api)
            except Exception:
                icon_uri = ""
        start_line["icon_uri"] = icon_uri
    else:
        start_line.setdefault("id_label", "NPCID")
        start_line.setdefault("icon_uri", "")
    end_line.setdefault("id_label", "NPCID")
    end_line.setdefault("icon_uri", "")

    objective_raw = desc.get("Objective") or quest.get("target") or ""
    description_raw = desc.get("Description") or quest.get("description") or ""
    objective_html = _segments_to_html(objective_raw)
    description_html = _segments_to_html(description_raw)

    need_items = _item_rows(quest.get("needItems") or [], item_meta)
    offer_items = _item_rows(quest.get("offerItems") or [], item_meta)

    quest_values: list[dict[str, str]] = []
    for v in quest.get("questValues") or []:
        if isinstance(v, dict) and str(v.get("str") or "").strip():
            quest_values.append(
                {"name": _escape(str(v.get("str"))), "amount": _escape(v.get("value", 1))}
            )

    kill_npcs: list[dict[str, str]] = []
    for k in quest.get("killNpcs") or []:
        if isinstance(k, dict):
            n = str(k.get("name") or k.get("id") or "").strip()
        else:
            n = str(k or "").strip()
        if n:
            kill_npcs.append({"name": _escape(n), "amount": "1"})

    rewards = quest.get("rewards") if isinstance(quest.get("rewards"), list) else []
    reward_cards = await _format_reward_cards(rewards, api=api)
    # Enrich item/achievement cards from item_meta / already embedded icon
    for rc in reward_cards:
        if not isinstance(rc, dict):
            continue
        if rc.get("kind") == "item":
            iid = str(rc.get("item_id") or "").strip()
            meta = (item_meta or {}).get(iid) or {}
            if meta.get("name"):
                rc["title"] = _escape(meta.get("name"))
            if meta.get("icon_uri"):
                rc["icon_uri"] = meta.get("icon_uri")
            rc["is_card"] = True
            # quality-ish color not required on quest cards
        elif rc.get("kind") in {"achievement", "skill"} and not rc.get("icon_uri"):
            # keep placeholder frame if download failed
            rc["icon_uri"] = _reward_icon_data_uri("train")


    chain_obj = quest.get("chain") or {}

    def _chain_rows(raw: Any) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for x in raw or []:
            if not isinstance(x, dict) or not x.get("visible", True):
                continue
            n = str(x.get("name") or "").strip()
            xid = str(x.get("id") or "")
            if not n:
                continue
            key = (xid, n)
            if key in seen:
                continue
            seen.add(key)
            result.append(
                {
                    "name": _escape(n),
                    "current": xid == str(qid) or n == name,
                }
            )
        return result

    chain_items = _chain_rows(chain_obj.get("current") if isinstance(chain_obj, dict) else [])
    if len(chain_items) == 1 and chain_items[0]["current"]:
        chain_items = []  # 链上只有自己时不展示任务链
    branch_items = _chain_rows(chain_obj.get("branch") if isinstance(chain_obj, dict) else [])

    qtype = str(quest.get("questType") or "").strip()
    if "【" not in name and (qtype == "repeat" or str(quest.get("difficulty") or "") == "重复"):
        name = name + "【重复】"
    desc_name = str(desc.get("QuestName") or "")
    if "【" not in name and "【" in desc_name:
        m2 = re.search(r"(【[^【】]+】)\s*$", desc_name)
        if m2:
            name = name + m2.group(1)
    m = re.match(r"^(.*?)【([^【】]+)】\s*$", name)
    if m:
        name_main, name_suffix = m.group(1), f"【{m.group(2)}】"
    else:
        name_main, name_suffix = name, ""

    return {
        "css": _load_css(),
        "viewport_width": content_width_for_kind("quest", quest=True),
        "qid": _escape(qid),
        "name_main": _escape(name_main),
        "name_suffix": _escape(name_suffix),
        "title_dark": not bool(name_suffix) and bool(quest.get("canShare")),
        "can_share": bool(quest.get("canShare")),
        "start_line": start_line,
        "end_line": end_line,
        "objective_html": objective_html,
        "description_html": description_html,
        "need_items": need_items,
        "offer_items": offer_items,
        "quest_values": quest_values,
        "kill_npcs": kill_npcs,
        "reward_cards": reward_cards,
        "chain_items": chain_items,
        "branch_items": branch_items,
    }


async def build_quest_html(
    quest: dict[str, Any],
    item_meta: dict[str, dict[str, Any]] | None = None,
    api: Any | None = None,
) -> str:
    data = await build_quest_template_data(quest, item_meta=item_meta, api=api)
    try:
        from jinja2 import Template

        return Template(QUEST_CARD_TMPL).render(**data)
    except Exception:
        # minimal fallback
        parts = [
            "<!DOCTYPE html><html><head><meta charset='utf-8'/><style>",
            data["css"],
            "</style></head><body><div id='quest-root'>",
            f"<div class='q-title'>{data['name_main']}<span class='q-id'>(ID:{data['qid']})</span></div>",
        ]
        if data["start_line"].get("where"):
            parts.append(f"<div class='q-node'><span class='label'>任务起点:</span> {data['start_line']['where']}</div>")
        if data["end_line"].get("where"):
            parts.append(f"<div class='q-node'><span class='label'>任务终点:</span> {data['end_line']['where']}</div>")
        if data["objective_html"]:
            parts.append("<div class='q-section-title'>任务目标</div>")
            parts.append(f"<div class='q-body'>{data['objective_html']}</div>")
        for it in data["need_items"]:
            parts.append(
                f"<div class='item-row'><span class='act'>收集</span>"
                f"<span class='name' style='color:{it['color']}'>{it['name']}</span>"
                f"<span class='amt'>× {it['amount']}</span></div>"
            )
        if data["description_html"]:
            parts.append("<div class='q-section-title'>任务描述</div>")
            parts.append(f"<div class='q-body'>{data['description_html']}</div>")
        for label, items in (("任务链", data["chain_items"]), ("任务分支", data["branch_items"])):
            if not items:
                continue
            parts.append(f"<div class='chain-label'>{label}</div><div class='chain-line'>")
            for i, c in enumerate(items):
                if i:
                    parts.append("<span class='chain-sep'>»</span>")
                cls = "chain-item current" if c["current"] else "chain-item"
                parts.append(f"<span class='{cls}'>[{c['name']}]</span>")
            parts.append("</div>")
        parts.append("</div></body></html>")
        return "".join(parts)


async def render_quest_card_html(
    star: Any,
    quest: dict[str, Any],
    *,
    item_meta: dict[str, dict[str, Any]] | None = None,
    return_url: bool = False,
    options: dict[str, Any] | None = None,
) -> str:
    """Render quest card via AstrBot Star.html_render (astrbot-t2i)."""
    data = await build_quest_template_data(quest, item_meta=item_meta, api=getattr(star, "api", None))
    if "viewport_width" not in data:
        data["viewport_width"] = content_width_for_kind("quest", quest=True)
    width = int(data.get("viewport_width") or 860)
    opts = build_t2i_options(width=width, base=QUEST_RENDER_OPTIONS, extra=options)
    result = await star.html_render(QUEST_CARD_TMPL, data, return_url=return_url, options=opts)
    if return_url or not result:
        return result
    local = str(result)
    if is_http_url(local):
        return local
    try:
        # light card: only crop transparent page margins, never white fill
        return crop_render_whitespace(local, dark_panel=False, pad=0)
    except Exception:
        return local


__all__ = [
    "QUEST_CARD_TMPL",
    "QUEST_RENDER_OPTIONS",
    "build_quest_html",
    "build_quest_template_data",
    "collect_quest_item_ids",
    "render_quest_card_html",
    "resolve_quest_item_meta",
]
