# -*- coding: utf-8 -*-
"""Item tip HTML multi-template for AstrBot html_render / t2i service."""
from __future__ import annotations

import base64
import html as html_lib
import io
from pathlib import Path
from typing import Any

from .font_util import simsun_embed_css
from .html_util import build_t2i_options, crop_render_whitespace, is_http_url, sanitize_css_color
from .item_tip import (
    C_STRENGTH,
    C_WHITE,
    _ASSETS as _ITEM_TIP_ASSETS,
    _build_rows,
    _is_weapon,
    _load_usage_icon,
    _type_label,
    is_true_equip,
)

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
_TEMPLATE_DIR = _PLUGIN_DIR / "assets" / "tip_templates"
_BASE_CSS = _TEMPLATE_DIR / "base.css"

_TIP_KINDS = (
    "equip",
    "weapon",
    "furniture",
    "consumable",
    "book",
    "material",
    "mount_pet",
    "appearance",
    "simple",
)
TIP_KINDS = _TIP_KINDS

# Base AstrBot html_render / t2i screenshot options for tip cards.
# Width is injected per render via build_t2i_options (t2i default viewport is 800px).
TIP_RENDER_OPTIONS: dict[str, Any] = {
    "full_page": True,
    "type": "png",
    "omit_background": True,
    "animations": "disabled",
    "caret": "hide",
    "scale": "device",
}

_FURNITURE_LABELS = {"家具", "景观", "收集", "建筑"}
_BOOK_LABELS = {
    "秘籍", "秘笈", "书籍", "心法", "内功", "外功", "轻功", "招式", "奇穴", "武学", "技法",
}
_MATERIAL_LABELS = {
    "材料", "矿石", "药材", "食材", "木材", "布料", "五彩石", "五行石", "增强", "道具强化", "碎石",
}
_MOUNT_LABELS = {"挂宠", "坐骑", "宠物"}
_APPEARANCE_LABELS = {
    "外观", "服饰", "发型", "脸型", "挂件", "背部挂件", "腰部挂件", "佩囊", "头饰", "面饰",
}
_CONSUMABLE_LABELS = {
    "药品", "食品", "食物", "消耗品", "礼盒", "宝箱", "盒子", "钥匙", "任务", "货币", "杂物", "烹饪", "酒",
}

# Jinja2 template consumed by AstrBot Star.html_render → t2i /generate
ITEM_TIP_TMPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width={{ viewport_width }}, initial-scale=1"/>
<style>{{ css | safe }}</style>
</head>
<body>
<div id="tip-root" class="kind-{{ kind }}{% if has_set %} has-set{% endif %}"{% if tip_width %} style="--tip-width: {{ tip_width }}px"{% endif %}>
  <div class="tip-inner">
  {% for row in rows %}
    {% if row.kind == "spacer" %}
    <div class="row row-spacer"></div>
    {% elif row.kind == "source_group" %}
    <div class="row row-source-group">
      <div class="left" style="color: {{ row.color }}">{{ row.text }}</div>
    </div>
    {% elif row.kind == "source_leaf" %}
    <div class="row row-source">
      <span class="source-arrow-css" aria-hidden="true"></span>
      <div class="left" style="color: {{ row.color }}">{{ row.text }}</div>
    </div>
{% elif row.kind == "usage" %}
    <div class="row row-usage">
      {% if row.icon_uri %}<img class="usage-icon" src="{{ row.icon_uri }}" alt=""/>{% endif %}
      <div class="left" style="color: {{ row.color }}">{{ row.text }}</div>
    </div>
    {% elif row.kind == "diamond" %}
    <div class="row row-diamond">
      <span class="diamond-box"></span>
      <div class="left" style="color: {{ row.color }}">{{ row.text }}</div>
    </div>
    {% elif row.kind == "horse_attr" %}
    <div class="row row-horse-attr">
      {% if row.icon_uri %}<img class="horse-icon" src="{{ row.icon_uri }}" alt=""/>{% endif %}
      <div class="horse-body">
        {% if row.title %}<div class="horse-title" style="color: {{ row.color }}">{{ row.title }}</div>{% endif %}
        {% if row.body %}<div class="horse-desc">{{ row.body }}</div>{% endif %}
      </div>
    </div>
    {% elif row.kind == "effect_ph" %}
    <div class="row row-effect-ph"><span class="effect-ph"></span></div>
    {% else %}
    <div class="row row-{{ row.kind }}">
      <div class="left{% if row.indent_dot %} indent-dot{% endif %}" style="color: {{ row.color }}{% if row.bold %}; font-weight: 700{% endif %}">{{ row.text }}</div>
      {% if row.right %}<div class="right" style="color: {{ row.right_color }}">{{ row.right }}</div>{% endif %}
    </div>
    {% endif %}
  {% endfor %}
  </div>
</div>
</body>
</html>
"""


def select_tip_kind(item: dict[str, Any]) -> str:
    """Pick a tip template kind for multi-template coverage."""
    type_label = _type_label(item)
    source = str(item.get("Source") or "").lower()
    name = str(item.get("Name") or "")
    desc = str(item.get("Desc") or "")

    if _is_weapon(item):
        return "weapon"

    is_furniture = (
        bool(item.get("furniture_attributes"))
        or source == "homeland"
        or type_label in _FURNITURE_LABELS
    )
    if is_furniture:
        return "furniture"

    # hang-pet / mount / appearance before bare IsEquip (API often marks them equip)
    if (
        type_label in _MOUNT_LABELS
        or name.startswith("挂宠")
        or "挂宠·" in name
        or "坐骑" in type_label
    ):
        return "mount_pet"
    if type_label in _APPEARANCE_LABELS or source in {"appearance", "exterior", "fashion"}:
        return "appearance"
    try:
        st = int(item.get("SubType")) if item.get("SubType") not in (None, "", "None") else None
    except Exception:
        st = None
    if st in {25, 30}:
        return "mount_pet"
    if st in {20, 21, 22, 23} and not is_true_equip(item):
        return "appearance"

    if is_true_equip(item):
        return "equip"

    if type_label in _BOOK_LABELS or "秘籍" in name or "秘笈" in name:
        return "book"
    if type_label in _MATERIAL_LABELS or source in {"material", "craft"}:
        return "material"
    if (
        type_label in _CONSUMABLE_LABELS
        or bool(item.get("CanConsume"))
        or source in {"box", "medicine", "food"}
        or any(k in name for k in ("茶", "酒", "丹", "药", "汤", "糕", "饼"))
        or ("使用" in desc and any(k in desc for k in ("恢复", "气血", "内力", "调息")))
    ):
        return "consumable"
    return "simple"


def _escape(text: Any) -> str:
    return html_lib.escape(str(text or ""), quote=True)


def _usage_icon_data_uri(icon_key: Any) -> str | None:
    icon = _load_usage_icon(icon_key)
    if icon is None:
        return None
    buf = io.BytesIO()
    icon.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"




def _source_arrow_data_uri() -> str:
    """Deprecated: tip template uses CSS triangles (.source-arrow-css)."""
    return ""

def _load_css() -> str:
    """Load tip CSS. Clarity comes from device_scale_factor=2 + CSS (not 8MB font embed)."""
    if _BASE_CSS.is_file():
        return _BASE_CSS.read_text(encoding="utf-8")
    return ""


def build_tip_template_data(item: dict[str, Any], kind: str | None = None) -> dict[str, Any]:
    """Build Jinja2 context for ITEM_TIP_TMPL."""
    kind = kind or select_tip_kind(item)
    if kind not in _TIP_KINDS:
        kind = "simple"

    raw_rows = _build_rows(item)
    has_set = isinstance(item.get("Set"), dict) and bool(item.get("Set"))
    tip_width = None  # 统一 375px 定宽（对齐游戏 tooltip 规格）

    rows: list[dict[str, Any]] = []
    for row in raw_rows:
        rkind = str(row.get("kind") or "normal")
        raw_text = str(row.get("text") or "")
        text = _escape(raw_text)
        color = sanitize_css_color(row.get("color") or C_WHITE, C_WHITE)
        right = str(row.get("right") or "")
        right_color = sanitize_css_color(
            row.get("right_color") or (C_STRENGTH if rkind == "title" else C_WHITE),
            C_STRENGTH if rkind == "title" else C_WHITE,
        )
        entry: dict[str, Any] = {
            "kind": rkind,
            "text": text,
            "color": color,
            "right": _escape(right) if right else "",
            "right_color": right_color,
            "icon_uri": "",
            "arrow": bool(row.get("arrow")),
            "bold": bool(row.get("bold")),
            "indent_dot": raw_text.startswith("·"),
            "title": "",
            "body": "",
        }
        if rkind == "usage":
            entry["icon_uri"] = _usage_icon_data_uri(row.get("icon_key")) or ""
        elif rkind == "horse_attr":
            icon_url = str(row.get("icon_url") or "").strip()
            icon_id = str(row.get("icon_id") or "").strip()
            if not icon_url and icon_id:
                icon_url = f"https://icon.jx3box.com/icon/{icon_id}.png"
            entry["icon_uri"] = icon_url
            entry["title"] = _escape(row.get("title") or row.get("text") or "")
            entry["body"] = _escape(row.get("body") or "")
            # keep left text as title for width estimator / fallbacks
            entry["text"] = entry["title"]
            entry["color"] = sanitize_css_color(row.get("color") or "#00D24B", "#00D24B")
        if rkind == "source_group":
            entry["kind"] = "source_group"
        elif rkind == "source_leaf" or row.get("arrow"):
            entry["kind"] = "source_leaf"
            entry["icon_uri"] = ""  # CSS triangle arrows; avoid fat SVG raster
            entry["arrow"] = True
        rows.append(entry)

    viewport_width = 375

    # 宋体子集内嵌：远端 t2i 无宋体也能渲染同款衬线
    chars: set[str] = set(str(item.get("Name") or ""))
    for r in rows:
        chars.update(str(r.get("text") or ""))
        chars.update(str(r.get("right") or ""))
        chars.update(str(r.get("title") or ""))
        chars.update(str(r.get("body") or ""))
    face = simsun_embed_css(frozenset(chars))
    css = face + "\n" + _load_css() if face else _load_css()

    return {
        "css": css,
        "kind": kind,
        "has_set": bool(has_set and kind in {"equip", "weapon"}),
        "tip_width": tip_width,
        "viewport_width": viewport_width,
        "rows": rows,
        "name": str(item.get("Name") or ""),
    }


def build_tip_html(item: dict[str, Any], kind: str | None = None) -> tuple[str, str]:
    """Render template locally with stdlib-like substitute for debug (no Jinja required).

    Returns (kind, html). Prefer AstrBot html_render in production.
    """
    data = build_tip_template_data(item, kind=kind)
    # Minimal local expand for offline debug without jinja2 dependency.
    try:
        from jinja2 import Template

        html = Template(ITEM_TIP_TMPL).render(**data)
    except Exception:
        # ultra-fallback: concatenate rows
        parts = [
            "<!DOCTYPE html><html><head><meta charset='utf-8'/><style>",
            data["css"],
            "</style></head><body>",
            f"<div id='tip-root' class='kind-{data['kind']}"
            + (" has-set" if data["has_set"] else "")
            + "'"
            + (f" style='--tip-width:{data['tip_width']}px'" if data["tip_width"] else "")
            + "><div class='tip-inner'>",
        ]
        for row in data["rows"]:
            if row["kind"] == "spacer":
                parts.append("<div class='row row-spacer'></div>")
            elif row["kind"] == "usage":
                icon = f"<img class='usage-icon' src='{row['icon_uri']}' alt=''/>" if row["icon_uri"] else ""
                parts.append(
                    f"<div class='row row-usage'>{icon}<div class='left' style='color:{row['color']}'>{row['text']}</div></div>"
                )
            elif row["kind"] == "diamond":
                parts.append(
                    f"<div class='row row-diamond'><span class='diamond-box'></span>"
                    f"<div class='left' style='color:{row['color']}'>{row['text']}</div></div>"
                )
            elif row["kind"] == "source_group":
                parts.append(
                    f"<div class='row row-source-group'><div class='left' style='color:{row['color']}'>{row['text']}</div></div>"
                )
            elif row["kind"] == "source_leaf":
                parts.append(
                    f"<div class='row row-source'><span class='source-arrow-css' aria-hidden='true'></span>"
                    f"<div class='left' style='color:{row['color']}'>{row['text']}</div></div>"
                )
            elif row["kind"] == "horse_attr":
                icon = f"<img class='horse-icon' src='{row['icon_uri']}' alt=''/>" if row.get("icon_uri") else ""
                title = row.get("title") or row.get("text") or ""
                body = row.get("body") or ""
                body_html = f"<div class='horse-desc'>{body}</div>" if body else ""
                title_html = f"<div class='horse-title' style='color:{row['color']}'>{title}</div>" if title else ""
                parts.append(
                    f"<div class='row row-horse-attr'>{icon}"
                    f"<div class='horse-body'>{title_html}{body_html}</div></div>"
                )
            else:
                right = (
                    f"<div class='right' style='color:{row['right_color']}'>{row['right']}</div>"
                    if row["right"]
                    else ""
                )
                parts.append(
                    f"<div class='row row-{row['kind']}'>"
                    f"<div class='left' style='color:{row['color']}'>{row['text']}</div>{right}</div>"
                )
        parts.append("</div></div></body></html>")
        html = "".join(parts)
    return data["kind"], html


async def render_item_tip_html(
    star: Any,
    item: dict[str, Any],
    *,
    kind: str | None = None,
    return_url: bool = False,
    options: dict[str, Any] | None = None,
) -> str:
    """Render tip image through AstrBot Star.html_render (remote/local t2i).

    star: plugin instance (self) providing html_render.
    returns: image url or local path depending on return_url.
    """
    data = build_tip_template_data(item, kind=kind)
    opts = build_t2i_options(width=375, base=TIP_RENDER_OPTIONS, extra=options)
    # AstrBot Star.html_render(tmpl, data, return_url=True, options=None)
    result = await star.html_render(ITEM_TIP_TMPL, data, return_url=return_url, options=opts)
    if return_url or not result:
        return result
    # Prefer local path so we can crop residual t2i margins.
    local = str(result)
    if is_http_url(local):
        try:
            # best-effort: if star exposes data dir / download helpers, skip; keep URL
            return local
        except Exception:
            return local
    try:
        return crop_render_whitespace(local, dark_panel=True, pad=0)
    except Exception:
        return local


def render_item_tip(item: dict[str, Any], icon_bytes: bytes | None, out_path: str | Path) -> str:
    """Sync API kept for smoke/debug only: writes HTML sibling, does not screenshot.

    Production path must use render_item_tip_html(self, item) via AstrBot t2i.
    """
    _ = icon_bytes
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    kind, html = build_tip_html(item)
    html_path = out_path.with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")
    # Placeholder 1x1 png so callers expecting a png path do not crash in offline smoke.
    # Real tip images come from html_render.
    try:
        from PIL import Image

        Image.new("RGB", (8, 8), (43, 61, 61)).save(out_path, format="PNG")
    except Exception:
        out_path.write_bytes(b"")
    return str(out_path)


__all__ = [
    "ITEM_TIP_TMPL",
    "TIP_KINDS",
    "TIP_RENDER_OPTIONS",
    "build_tip_html",
    "build_tip_template_data",
    "render_item_tip",
    "render_item_tip_html",
    "select_tip_kind",
]
