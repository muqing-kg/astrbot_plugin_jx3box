# -*- coding: utf-8 -*-
"""Quest detail HTML multi-template for AstrBot html_render / astrbot-t2i."""
from __future__ import annotations

import base64
import html as html_lib
import io
from pathlib import Path
from typing import Any

from .html_util import sanitize_css_color
from .item_tip import QUALITY_COLORS
from .renderers import (
    _QUEST_TYPE_LABELS,
    _format_rewards,
    parse_tag_to_plain,
    parse_tags,
)

_PLUGIN_DIR = Path(__file__).resolve().parent
_TEMPLATE_DIR = _PLUGIN_DIR / "assets" / "quest_templates"
_BASE_CSS = _TEMPLATE_DIR / "base.css"

# Light-theme tag colors closer to jx3box quest page
_LIGHT_TAG_COLORS = {
    "G": "#16a34a",
    "F171": "#d97706",
    "F172": "#dc2626",
    "F173": "#2563eb",
    "F174": "#059669",
    "N": "#d97706",
    "DEFAULT": "#3c4048",
}

QUEST_RENDER_OPTIONS: dict[str, Any] = {
    "full_page": True,
    "type": "png",
    "omit_background": False,
    "animations": "disabled",
}

QUEST_CARD_TMPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<style>{{ css | safe }}</style>
</head>
<body>
<div id="quest-root">
  <div class="q-head">
    <div class="q-title-wrap">
      <div class="q-title">{{ name }}<span class="q-id">(ID:{{ qid }})</span></div>
      {% if start_line %}<div class="q-meta"><span class="label">任务起点:</span> {{ start_line }}</div>{% endif %}
      {% if end_line %}<div class="q-meta"><span class="label">任务终点:</span> {{ end_line }}</div>{% endif %}
      {% if tags %}
      <div class="q-tags">
        {% for t in tags %}<span class="q-tag">{{ t }}</span>{% endfor %}
      </div>
      {% endif %}
    </div>
    {% if difficulty %}<div class="q-badge">{{ difficulty }}</div>{% endif %}
  </div>

  <hr class="q-divider"/>

  {% if objective_html or need_items or kill_npcs %}
  <section class="q-section">
    <div class="q-section-title"><span class="tri"></span>任务目标</div>
    {% if objective_html %}<div class="q-body">{{ objective_html | safe }}</div>{% endif %}
    {% for it in need_items %}
    <div class="item-row">
      <span class="act">收集</span>
      {% if it.icon_uri %}<img class="icon" src="{{ it.icon_uri }}" alt=""/>{% else %}<span class="icon-ph"></span>{% endif %}
      <span class="item-main">
        <span class="name" style="color:{{ it.color }}">{{ it.name }}</span>
        <span class="amt">× {{ it.amount }}</span>
      </span>
    </div>
    {% endfor %}
    {% for k in kill_npcs %}
    <div class="obj-line"><span class="prefix">击败</span><span>{{ k }}</span></div>
    {% endfor %}
  </section>
  <hr class="q-divider"/>
  {% endif %}

  {% if description_html %}
  <section class="q-section">
    <div class="q-section-title"><span class="tri"></span>任务描述</div>
    <div class="q-body">{{ description_html | safe }}</div>
  </section>
  <hr class="q-divider"/>
  {% endif %}

  {% if offer_items %}
  <section class="q-section">
    <div class="q-section-title"><span class="tri"></span>提供物品</div>
    {% for it in offer_items %}
    <div class="item-row" style="margin-left:0">
      {% if it.icon_uri %}<img class="icon" src="{{ it.icon_uri }}" alt=""/>{% else %}<span class="icon-ph"></span>{% endif %}
      <span class="item-main">
        <span class="name" style="color:{{ it.color }}">{{ it.name }}</span>
        <span class="amt">× {{ it.amount }}</span>
      </span>
    </div>
    {% endfor %}
  </section>
  <hr class="q-divider"/>
  {% endif %}

  {% if reward_cards %}
  <section class="q-section">
    <div class="q-section-title"><span class="tri"></span>任务奖励</div>
    <div class="reward-extras">
      {% for r in reward_cards if (not r.is_card) and r.kind in ["item_group_tip", "exp", "money", "affect"] %}
      {% if r.kind == "item_group_tip" %}<div class="reward-extra reward-tip">{{ r.title }}</div>{% endif %}
      {% endfor %}
    </div>
    <div class="reward-grid">
      {% for r in reward_cards if r.is_card %}
      <div class="reward-card">
        {% if r.icon_uri %}<img class="reward-icon" src="{{ r.icon_uri }}" alt=""/>{% else %}<span class="reward-icon-ph"></span>{% endif %}
        <div class="reward-text">
          <div class="reward-title">{{ r.title }}</div>
          {% if r.amount %}<div class="reward-amt">{{ r.amount }}</div>{% endif %}
        </div>
      </div>
      {% endfor %}
    </div>
    <div class="reward-extras">
      {% for r in reward_cards if (not r.is_card) and r.kind not in ["item_group_tip"] %}
      <div class="reward-extra">{% if r.html %}{{ r.html | safe }}{% else %}{{ r.title }}{% endif %}</div>
      {% endfor %}
    </div>
  </section>
  <hr class="q-divider"/>
  {% endif %}

  {% if chain_items %}
  <section class="q-section chain-wrap">
    <div class="chain-label">任务链</div>
    <div class="chain-line">
      {% for c in chain_items %}
        {% if not loop.first %}<span class="chain-sep">»</span>{% endif %}
        <span class="chain-item{% if c.current %} current{% endif %}">[{{ c.name }}]</span>
      {% endfor %}
    </div>
  </section>
  {% endif %}
</div>
</body>
</html>
"""


def _escape(text: Any) -> str:
    return html_lib.escape(str(text or ""), quote=True)


def _load_css() -> str:
    if _BASE_CSS.is_file():
        return _BASE_CSS.read_text(encoding="utf-8")
    return ""


def _npc_line(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    map_name = str(node.get("mapName") or "").strip()
    name = str(node.get("name") or "").strip()
    nid = node.get("id")
    left = "·".join([x for x in [map_name, name] if x])
    if not left:
        return ""
    if nid not in (None, ""):
        return f"{left}（NPCID: {nid}）"
    return left


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

    # remap colors to light theme
    html_parts: list[str] = []
    buf: list[str] = []
    for text, color in segs:
        if text == "\n":
            para = "".join(buf).strip()
            if para:
                html_parts.append(f"<p>{para}</p>")
            elif html_parts:
                html_parts.append("<p><br/></p>")
            buf = []
            continue
        c = color
        # map dark-theme defaults
        if color in {"#D7DCE5", "#7FDBA8", "#FFD76A", "#FF7A6B", "#6EC8FF", "#B7F0B0", "#F6D36A"}:
            # reverse map via approximate
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
        # If parse_tags already gave hex from _TAG_COLORS dark, remapped above
        buf.append(f'<span style="color:{c}">{_escape(text)}</span>')
    para = "".join(buf).strip()
    if para:
        html_parts.append(f"<p>{para}</p>")
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
        # try bare numeric id with common prefixes
        if not detail:
            bare = iid.split("_")[-1] if "_" in iid else iid
            for cand in [f"5_{bare}", f"8_{bare}", f"6_{bare}", f"7_{bare}", bare]:
                if cand == iid:
                    continue
                try:
                    detail = await api.get_item(cand)
                except Exception:
                    detail = None
                if detail:
                    break
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

    for iid in collect_quest_item_ids(quest):
        meta[iid] = await _load_one(str(iid))
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
        amount = it.get("amount", 1)
        m = item_meta.get(iid) or {}
        rows.append(
            {
                "id": iid,
                "name": _escape(m.get("name") or iid),
                "amount": amount,
                "color": sanitize_css_color(m.get("color") or "#2563eb", "#2563eb"),
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
                "amount": f"× {c}",
                "icon_uri": _reward_icon_data_uri(typ),
                "is_card": True,
                "html": "",
                "item_id": "",
            })
            continue

        if typ == "exp":
            extras.append({
                "kind": "exp",
                "title": f"获得阅历：{c}",
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
                "title": f"获得声望（{force}）{sign}{n}",
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
                "title": name,
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
                "title": name,
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
                amt = it.get("amount", 1)
                cards.append({
                    "kind": "item",
                    "title": iid,  # replaced later with real name
                    "amount": f"× {amt}",
                    "icon_uri": "",
                    "is_card": True,
                    "html": "",
                    "item_id": iid,
                })
            continue

        if typ:
            extras.append({
                "kind": typ,
                "title": f"{typ} {c}",
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
    difficulty = quest.get("difficulty") or desc.get("Difficulty") or ""
    difficulty = str(difficulty).strip() if difficulty not in (None, "") else ""

    start_line = _npc_line(quest.get("start") or {})
    end_line = _npc_line(quest.get("end") or {})

    quest_type = str(quest.get("questType") or "").strip()
    school_name = str(quest.get("schoolName") or "").strip()
    tags: list[str] = []
    type_label = _QUEST_TYPE_LABELS.get(quest_type, quest_type)
    if type_label:
        tags.append(type_label)
    if school_name:
        tags.append(school_name)
    if quest.get("canShare"):
        tags.append("可共享")
    if quest.get("canAssist"):
        tags.append("可援助")
    # unique
    uniq: list[str] = []
    for t in tags:
        if t and t not in uniq:
            uniq.append(t)

    objective_html = _segments_to_html(desc.get("Objective") or "")
    description_html = _segments_to_html(desc.get("Description") or "")

    need_items = _item_rows(quest.get("needItems") or [], item_meta)
    offer_items = _item_rows(quest.get("offerItems") or [], item_meta)

    kill_npcs: list[str] = []
    for k in quest.get("killNpcs") or []:
        if isinstance(k, dict):
            n = str(k.get("name") or k.get("id") or "").strip()
        else:
            n = str(k or "").strip()
        if n:
            kill_npcs.append(_escape(n))

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
                rc["title"] = meta.get("name")
            if meta.get("icon_uri"):
                rc["icon_uri"] = meta.get("icon_uri")
            rc["is_card"] = True
            # quality-ish color not required on quest cards
        elif rc.get("kind") in {"achievement", "skill"} and not rc.get("icon_uri"):
            # keep placeholder frame if download failed
            rc["icon_uri"] = _reward_icon_data_uri("train")


    chain = ((quest.get("chain") or {}).get("current")) or []
    chain_items: list[dict[str, Any]] = []
    for x in chain:
        if not isinstance(x, dict) or not x.get("visible", True):
            continue
        n = str(x.get("name") or "").strip()
        if not n:
            continue
        chain_items.append(
            {
                "name": _escape(n),
                "current": str(x.get("id")) == str(qid) or n == name,
            }
        )

    return {
        "css": _load_css(),
        "qid": _escape(qid),
        "name": _escape(name),
        "difficulty": _escape(difficulty),
        "start_line": _escape(start_line),
        "end_line": _escape(end_line),
        "tags": [_escape(t) for t in uniq],
        "objective_html": objective_html,
        "description_html": description_html,
        "need_items": need_items,
        "offer_items": offer_items,
        "kill_npcs": kill_npcs,
        "reward_cards": reward_cards,
        "chain_items": chain_items,
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
            f"<div class='q-title'>{data['name']}<span class='q-id'>(ID:{data['qid']})</span></div>",
        ]
        if data["start_line"]:
            parts.append(f"<div class='q-meta'>任务起点: {data['start_line']}</div>")
        if data["end_line"]:
            parts.append(f"<div class='q-meta'>任务终点: {data['end_line']}</div>")
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
        if data["chain_items"]:
            parts.append("<div class='chain-label'>任务链</div><div class='chain-line'>")
            for i, c in enumerate(data["chain_items"]):
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
    opts = dict(QUEST_RENDER_OPTIONS)
    if options:
        opts.update(options)
    return await star.html_render(QUEST_CARD_TMPL, data, return_url=return_url, options=opts)


__all__ = [
    "QUEST_CARD_TMPL",
    "QUEST_RENDER_OPTIONS",
    "build_quest_html",
    "build_quest_template_data",
    "collect_quest_item_ids",
    "render_quest_card_html",
    "resolve_quest_item_meta",
]
