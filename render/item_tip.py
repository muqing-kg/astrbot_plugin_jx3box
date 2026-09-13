# -*- coding: utf-8 -*-
"""物品 tip 高保真本地复刻（对齐 JX3BOX c-item-wrapper）。"""
from __future__ import annotations

import html as html_lib
import re
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from .font_util import get_font
from ..api.jx3_api import ICON, clean_desc

# 品质色（对齐官网 tip 实测）
QUALITY_COLORS = {
    # Official @jx3box/jx3box-ui assets/js/item/color.js
    0: "#A7A7A7",
    1: "#FFFFFF",
    2: "#00D24B",
    3: "#007EFF",
    4: "#FE2DFE",
    5: "#FFA500",
}

# tip 配色
C_BG = (15, 34, 34, 224)  # rgba(15,34,34,0.88) from item.less
C_BORDER = (15, 34, 34, 255)
C_WHITE = "#FFFFFF"
C_GREEN = "#00D24B"  # .u-green
C_GREEN2 = "#00D24B"
C_YELLOW = "#FFFF00"  # .u-yellow
C_ORANGE = "#FFA500"  # .u-orange / quality 5
C_GRAY = "#ADADAD"  # .u-gray
C_STRENGTH = "#7EE3A3"  # .u-max-strength-level
C_DESC = "#FFFF00"
C_EXIST = "#CFCFCF"  # .u-max-exist-time
C_SOURCE_HEADER = "#FFA500"  # orange header for 获取途径
C_SOURCE_LEAF = "#00D24B"

EQUIP_USAGE = {
    1: "秘境挑战",
    2: "竞技对抗",
    3: "休闲",
    4: "日常",
    5: "活动",
}

# 菜单/字段缺失时的 TypeLabel 兜底（AucGenre, AucSubType）
_AUC_TYPE_LABEL = {
    (1, 1): "棍类",
    (1, 2): "长兵类",
    (1, 3): "短兵类",
    (1, 5): "双兵类",
    (1, 6): "笔类",
    (1, 7): "重兵类",
    (1, 8): "虫笛类",
    (1, 9): "千机匣",
    (1, 10): "弯刀",
    (1, 11): "棒",
    (1, 12): "盾刀",
    (1, 13): "琴",
    (1, 14): "傲霜刀",
    (1, 15): "伞",
    (1, 16): "链刃",
    (1, 17): "魂灯",
    (1, 18): "百草卷",
    (1, 19): "横刀",
    (1, 20): "弓箭",
    (1, 21): "扇",
    (2, 1): "投掷",
    (2, 2): "弓弦",
    (2, 4): "弹药",
    (3, 1): "上衣",
    (3, 2): "帽子",
    (3, 3): "腰带",
    (3, 4): "下装",
    (3, 5): "鞋子",
    (3, 6): "护腕",
    (4, 1): "项链",
    (4, 2): "戒指",
    (4, 3): "腰坠",
    (4, 4): "腰部挂件",
    (4, 5): "背部挂件",
    (4, 6): "披风",
    (5, 1): "坐骑",
    (5, 2): "坐骑头饰",
    (5, 3): "坐骑胸饰",
    (5, 4): "坐骑足饰",
    (5, 5): "坐骑鞍饰",
    (5, 6): "坐骑幼崽",
    (5, 13): "坐骑",
    (5, -1): "奇趣坐骑",
    (6, 1): "背包",
    (7, None): "秘笈",
    (8, 1): "缝纫配方",
    (8, 2): "烹饪配方",
    (8, 3): "医术配方",
    (8, 4): "铸造配方",
    (9, 1): "食物",
    (9, 2): "药品",
    (9, 3): "礼品",
    (9, 4): "草料",
    (9, 5): "兵鉴",
    (10, None): "材料",
    (12, 1): "杂集",
    (12, 2): "道学",
    (12, 3): "佛学",
    (13, None): "物品强化",
    (14, 1): "瑰石",
    (14, 2): "其他",
    (15, 1): "五行石",
    (15, 2): "五彩石",
    (16, 1): "宝箱",
    (16, 2): "钥匙",
    (20, 1): "垃圾",
    (20, 2): "其他",
    (21, 1): "建筑",
    (21, 2): "家具",
    (21, 3): "景观",
    (21, 4): "收集",
    (22, 3): "外观",
    (22, 4): "奇趣坐骑",
    (22, 5): "外观",
    (22, 10): "挂宠",
    (22, 11): "礼盒",
    (22, 12): "外观",
    (25, 1): "钥匙",
    (26, 3): "兵刃",
    (26, 11): "项链",
    (26, 14): "钥匙",
    (26, 15): "钥匙",
    (26, None): "其他",
    (99, None): "其他",
    (99, 0): "宝箱",
    (99, 1): "药品",
    (99, 5): "材料",
    (99, 10): "材料",
    (99, 11): "材料",
}

_SUBTYPE_LABEL = {
    11: "配方",
    14: "奇趣坐骑",
    15: "坐骑",
    20: "腰部挂件",
    21: "背部挂件",
    22: "披风",
    23: "坐骑饰品",
    25: "挂宠",
    30: "挂宠",
}

_NO_USAGE_LABELS = {
    "家具",
    "景观",
    "收集",
    "建筑",
    "坐骑",
    "坐骑幼崽",
    "坐骑胸饰",
    "坐骑鞍饰",
    "坐骑头饰",
    "坐骑足饰",
    "奇趣坐骑",
    "坐骑饰品",
    "背包",
    "挂宠",
    "宝箱",
    "钥匙",
    "配方",
    "缝纫配方",
    "烹饪配方",
    "医术配方",
    "铸造配方",
    "材料",
    "药品",
    "食物",
    "礼品",
    "草料",
    "兵鉴",
    "秘籍",
    "秘笈",
    "杂集",
    "道学",
    "佛学",
    "五行石",
    "五彩石",
    "物品强化",
    "瑰石",
    "垃圾",
    "外观",
    "任务物品",
    "消耗品",
    "礼盒",
    "令牌",
    "提品",
    "装备提品",
    "其他",
    "饰品",
}


# 外观/挂宠等伪装备：接口常标 IsEquip，但 tip 不应走真装备宽板与精炼栏
_PSEUDO_EQUIP_SUBTYPES = {14, 15, 20, 21, 22, 23, 25, 30}
_HIDE_TYPE_LABELS = {
    "挂宠",
    "坐骑",
    "奇趣坐骑",
    "坐骑饰品",
    "坐骑头饰",
    "坐骑胸饰",
    "坐骑鞍饰",
    "坐骑足饰",
    "腰部挂件",
    "背部挂件",
    "披风",
    "宠物",
}
_MOUNT_LABELS_LOCAL = {"挂宠", "坐骑", "宠物", "奇趣坐骑"}


def _subtype_int(item: dict[str, Any]) -> int | None:
    try:
        st = item.get("SubType")
        if st in (None, "", "None"):
            return None
        return int(st)
    except Exception:
        return None


def _max_strength_value(item: dict[str, Any]) -> int | None:
    """Return positive max strength only; 0/None means no refine line on tip."""
    raw = item.get("MaxStrengthLevel")
    if raw in (None, "", "None"):
        return None
    try:
        val = int(raw)
    except Exception:
        return None
    if val <= 0:
        return None
    return val


def is_true_equip(item: dict[str, Any]) -> bool:
    """Real gear that uses equip tip width / refine / durability semantics."""
    # weapons always
    source = str(item.get("Source") or "").strip().lower()
    if source == "weapon":
        return True
    try:
        g = int(item.get("AucGenre"))
        if g == 1:
            return True
        if g == 26 and int(item.get("AucSubType") or -1) == 3:
            return True
    except Exception:
        pass

    type_label = _type_label(item)
    name = str(item.get("Name") or "")
    st = _subtype_int(item)

    if type_label in _HIDE_TYPE_LABELS or type_label in _MOUNT_LABELS_LOCAL:
        return False
    if name.startswith("挂宠") or "挂宠·" in name:
        return False
    if st in {25, 30}:
        return False
    if st in _PSEUDO_EQUIP_SUBTYPES and _max_strength_value(item) is None and not item.get("attributes"):
        return False

    if source in {"weapon", "armor", "hero_equip"}:
        return True

    strength = _max_strength_value(item)
    if strength is not None:
        return True
    if item.get("attributes") and source in {"weapon", "armor", "trinket", "hero_equip"}:
        return True
    # classic equip trinkets with strength already handled; bare IsEquip hang-like → false
    if item.get("IsEquip") and source == "trinket" and strength is None and not item.get("attributes"):
        return False
    return bool(item.get("IsEquip") and (strength is not None or bool(item.get("attributes"))))


_ASSETS = Path(__file__).resolve().parent / "assets" / "item_tip"

_RE_TEXT_FONT = re.compile(
    r'text\s*=\s*"((?:\\.|[^"\\])*)"(?:[^<>]*?font\s*=\s*(\d+))?',
    re.I | re.S,
)
_RE_TAG = re.compile(r"<[^>]+>")
_RE_WS = re.compile(r"[ \t\r\f\v]+")
_RE_COLOR_RGB = re.compile(r"color\s*:\s*rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", re.I)
_RE_COLOR_HEX = re.compile(r"color\s*:\s*#([0-9a-fA-F]{3,8})", re.I)


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _text_w(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    try:
        return int(draw.textlength(text, font=font))
    except Exception:
        box = draw.textbbox((0, 0), text, font=font)
        return int(box[2] - box[0])


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    text = (text or "").replace("\r", "")
    if not text:
        return []
    lines: list[str] = []
    for para in text.split("\n"):
        if not para:
            lines.append("")
            continue
        cur = ""
        for ch in para:
            trial = cur + ch
            if _text_w(draw, trial, font) <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = ch
        if cur:
            lines.append(cur)
    return lines


def _load_usage_icon(equip_usage: Any) -> Image.Image | None:
    try:
        key = int(equip_usage)
    except Exception:
        return None
    path = _ASSETS / f"usage_{key}.png"
    if not path.exists():
        return None
    try:
        img = Image.open(path).convert("RGBA")
        # official crops bake tip panel bg (~43,61,61); punch to alpha
        px = img.load()
        w, h = img.size
        for y in range(h):
            for x in range(w):
                r, g, b, a = px[x, y]
                if a == 0:
                    continue
                if abs(r - 43) <= 20 and abs(g - 61) <= 20 and abs(b - 61) <= 20:
                    px[x, y] = (0, 0, 0, 0)
                elif abs(r - 15) <= 14 and abs(g - 34) <= 14 and abs(b - 34) <= 14:
                    px[x, y] = (0, 0, 0, 0)
        # keep sharp small icon; tip row icons are ~15-16px
        if max(img.size) > 18:
            img = img.resize((16, 16), Image.Resampling.LANCZOS)
        elif img.size != (16, 16) and abs(img.size[0]-16) <= 2:
            img = img.resize((16, 16), Image.Resampling.NEAREST)
        return img
    except Exception:
        return None


def _unescape_text(text: str) -> str:
    s = str(text or "")
    s = s.replace("\\\\n", "\n").replace("\\n", "\n")
    s = s.replace("\\\\", "")
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = html_lib.unescape(s)
    s = _RE_WS.sub(" ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    # cleanup leftover escape backslashes from Desc payloads
    s = s.replace("\\", "")
    return s.strip()



def _font_color(font: Any, default: str = C_DESC) -> str:
    key = str(font or "").strip()
    if key == "105":
        return C_GREEN
    if key == "101":
        return C_ORANGE
    if key in {"100", "0", ""}:
        return default
    return default


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02X}{g:02X}{b:02X}"


def _style_color(style: str, default: str = C_WHITE) -> str:
    m = _RE_COLOR_RGB.search(style or "")
    if m:
        r, g, b = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if g >= 160 and r <= 80 and b <= 120:
            return C_GREEN
        return _rgb_to_hex(r, g, b)
    m = _RE_COLOR_HEX.search(style or "")
    if m:
        hx = m.group(1)
        if len(hx) == 3:
            hx = "".join(ch * 2 for ch in hx)
        if len(hx) >= 6:
            return f"#{hx[:6].upper()}"
    return default


def _plain_text(raw: Any) -> str:
    s = str(raw or "")
    if not s:
        return ""
    s = re.sub(r"<\s*SpiStone\b[^>]*>", "", s, flags=re.I)
    parts = re.findall(r'text\s*=\s*"((?:\\.|[^"\\])*)"', s, flags=re.I)
    if parts:
        s = "\n".join(parts)
    s = _RE_TAG.sub("", s)
    s = _unescape_text(s)
    s = s.replace("text=", "").strip()
    s = re.sub(r"font=\d+", "", s).strip()
    return s


def _rich_segments(raw: Any, default_color: str = C_WHITE) -> list[tuple[str, str]]:
    """把 tip 中常见 HTML / Text 标签解析成 (text, color) 段。"""
    if raw in (None, ""):
        return []
    s = str(raw)
    # 清理客户端特殊标签残留
    s = re.sub(r"<\s*SpiStone\b[^>]*>", "", s, flags=re.I)
    segs: list[tuple[str, str]] = []

    if "text=" in s.lower():
        # 带上下文抓取，识别 iteminfolink
        parts = list(re.finditer(
            r'text\s*=\s*"((?:\\.|[^"\\])*)"([^<>]*)',
            s,
            flags=re.I | re.S,
        ))
        if parts:
            merged: list[tuple[str, str]] = []
            for m in parts:
                text = _unescape_text(m.group(1))
                if not text:
                    continue
                tail = m.group(2) or ""
                fm = re.search(r"font\s*=\s*(\d+)", tail, flags=re.I)
                font = fm.group(1) if fm else ""
                color = _font_color(font, default=default_color)
                is_link = "iteminfolink" in tail.lower() or 'name="iteminfolink"' in s[m.start(): m.end() + 80].lower()
                if str(font) == "105" or text.startswith("使用"):
                    color = C_GREEN
                elif is_link or (not font and (text.startswith("[") or text in {"、", "，", ",", " "})):
                    color = merged[-1][1] if merged else C_GREEN
                if str(font) == "101":
                    color = C_ORANGE

                # 同色且无显式换行时拼接，还原官网连续描述
                if (
                    merged
                    and merged[-1][1] == color
                    and "\n" not in text
                    and not merged[-1][0].endswith(("\n", "。", "！", "？"))
                ):
                    # 如果上一段已是完整句且当前是新“使用”则不拼
                    if text.startswith("使用") and merged[-1][0]:
                        merged.append((text, color))
                    else:
                        merged[-1] = (merged[-1][0] + text, color)
                else:
                    merged.append((text, color))
            for text, color in merged:
                for line in text.splitlines():
                    line = line.strip()
                    if line:
                        segs.append((line, color))
            if segs:
                return segs

    if re.search(r"<\s*(span|div)\b", s, flags=re.I):
        pos = 0
        for m in re.finditer(r"<\s*(span|div)\b([^>]*)>(.*?)</\s*\1\s*>", s, flags=re.I | re.S):
            if m.start() > pos:
                pre = _plain_text(s[pos : m.start()])
                for line in pre.splitlines():
                    line = line.strip()
                    if line:
                        segs.append((line, default_color))
            tag = m.group(1).lower()
            attrs = m.group(2) or ""
            body = _plain_text(m.group(3))
            if body:
                color = _style_color(attrs, default=C_GREEN) if tag == "span" else default_color
                for line in body.splitlines():
                    line = line.strip()
                    if line:
                        segs.append((line, color))
            pos = m.end()
        if pos < len(s):
            tail = _plain_text(s[pos:])
            for line in tail.splitlines():
                line = line.strip()
                if line:
                    segs.append((line, default_color))
        if segs:
            return segs

    plain = _plain_text(s) or clean_desc(s)
    for line in plain.splitlines():
        line = line.strip()
        if line:
            segs.append((line, default_color))
    return segs


def _type_label(item: dict[str, Any]) -> str:
    """优先接口 TypeLabel，缺失时按拍卖分类/子类/名称兜底。"""
    raw = str(item.get("TypeLabel") or "").strip()
    if raw and raw not in {"未知", "其他"}:
        # “其他”太泛，后面再尝试更精确映射；先保留非空精确值
        if raw != "其他":
            return raw

    try:
        genre = item.get("AucGenre")
        sub = item.get("AucSubType")
        if genre is not None and str(genre) not in {"", "None"}:
            g = int(genre)
            s = int(sub) if sub not in (None, "", "None") else None
            if (g, s) in _AUC_TYPE_LABEL:
                return _AUC_TYPE_LABEL[(g, s)]
            if (g, None) in _AUC_TYPE_LABEL:
                return _AUC_TYPE_LABEL[(g, None)]
    except Exception:
        pass

    try:
        st = item.get("SubType")
        if st not in (None, "", "None"):
            st_i = int(st)
            if st_i in _SUBTYPE_LABEL:
                return _SUBTYPE_LABEL[st_i]
    except Exception:
        pass

    name = str(item.get("Name") or "")
    if name.startswith("挂宠") or "挂宠·" in name:
        return "挂宠"
    if "宝箱" in name:
        return "宝箱"
    if "礼盒" in name or "礼包" in name or name.endswith("宝匣") or "宝藏" in name:
        return "礼盒"
    if "券" in name or "背包位" in name:
        return "消耗品"
    if "信件" in name or "书信" in name:
        return "其他"
    if "铁棒" in name or "废弃" in name:
        return "垃圾"
    if "钥匙" in name:
        return "钥匙"
    if "配方" in name or name.endswith("制法"):
        return "配方"
    if "秘籍" in name or "秘笈" in name:
        return "秘籍"
    if "五行石" in name:
        return "五行石"
    if "五彩石" in name:
        return "五彩石"
    if "垃圾" in name:
        return "垃圾"
    if "令牌" in name:
        return "令牌"
    if "经验书" in name or name.startswith("道学"):
        return "道学"
    if name.startswith("打包的") or "小炒" in name or "农家" in name or "红茶" in name or name.endswith("茶"):
        return "食物"
    if "厨神" in name or "炊·" in name or "物同价异" in name:
        return "其他"
    if "管家契约" in name or name.startswith("管家"):
        return "其他"
    if "印象】" in name or name.startswith("【印象】"):
        return "材料"
    if (
        "·武器" in name
        or "·暗器" in name
        or "·鞋子" in name
        or "·下装" in name
        or "·护腕" in name
        or "矿髓" in name
        or "古岩" in name
        or "古玉" in name
    ):
        desc = str(item.get("Desc") or "")
        if "对装备使用" in desc or "提品" in desc or "提品" in name:
            return "装备提品"
    desc = str(item.get("Desc") or "")
    desc_use = "使用：" in desc or 'text="使用' in desc
    if item.get("CanConsume") is True or desc_use:
        if "药剂" in desc or "一饮而尽" in desc:
            return "药品"
        if "礼盒" in name or "礼包" in name or name.endswith("宝匣") or "宝藏" in name:
            return "礼盒"
        return "消耗品"
    if str(item.get("Source") or "").lower() == "trinket" and item.get("IsEquip"):
        return "饰品"

    if raw:
        return raw
    if item.get("IsQuest"):
        return "任务物品"
    return ""


def _bind_text(item: dict[str, Any]) -> str:
    bind = item.get("BindType")
    can_trade = item.get("CanTrade")
    if bind in (2, 3) or can_trade is False:
        return "不可交易"
    return ""


def _usage_text(item: dict[str, Any]) -> str:
    """仅真实装备展示用途；坐骑/挂宠/家具/消耗等不显示。"""
    type_label = _type_label(item)
    if type_label in _NO_USAGE_LABELS:
        return ""

    source = str(item.get("Source") or "").lower()
    if source in {"other", "homeland"}:
        return ""

    try:
        sub = item.get("SubType")
        if sub not in (None, "", "None") and int(sub) in {14, 15, 20, 21, 22, 23, 25, 30}:
            # 挂宠/坐骑/挂件/披风等外观向
            if not item.get("MaxStrengthLevel"):
                return ""
    except Exception:
        pass

    # 没有精炼等级的“伪装备”不显示用途
    if item.get("MaxStrengthLevel") in (None, "", 0, "0") and not (
        source in {"weapon", "armor", "trinket", "hero_equip"} and item.get("attributes")
    ):
        # 饰品/防具/武器有 attributes 才算
        if source not in {"weapon", "armor", "trinket", "hero_equip"}:
            return ""
        if not item.get("attributes"):
            return ""

    # 挂宠名称兜底
    name = str(item.get("Name") or "")
    if name.startswith("挂宠"):
        return ""

    try:
        return EQUIP_USAGE.get(int(item.get("EquipUsage")), "")
    except Exception:
        return ""


def _cooldown_text(cool: Any) -> str:
    if cool in (None, ""):
        return ""
    try:
        sec = int(cool)
    except Exception:
        return f"使用间隔{cool}"
    if sec <= 0:
        return ""
    if sec % 3600 == 0:
        return f"使用间隔{sec // 3600}小时"
    if sec % 60 == 0:
        return f"使用间隔{sec // 60}分钟"
    return f"使用间隔{sec}秒"


def _exist_time_text(ts: Any) -> str:
    """MaxExistTime 既可能是持续秒数，也可能是绝对时间戳。

    - 持续秒数（如 600 / 172800 / 2592000）→ 限时时间：x分钟/小时/天
    - 绝对时间戳（>= 1e9）且已过期 → 限时时间：已失效
    - 绝对时间戳且未过期 → 限时时间：剩余 x 天/小时/分钟/秒
    """
    if ts in (None, "", 0, "0"):
        return ""
    try:
        val = int(ts)
    except Exception:
        return f"限时时间：{ts}"

    # Unix 时间戳（约 2001-09 之后）
    if val >= 1_000_000_000:
        now = int(time.time())
        if val <= now:
            return "限时时间：已失效"
        remain = val - now
        if remain >= 86400:
            return f"限时时间：{remain // 86400}天"
        if remain >= 3600:
            return f"限时时间：{remain // 3600}小时"
        if remain >= 60:
            return f"限时时间：{remain // 60}分钟"
        return f"限时时间：{remain}秒"

    # 持续秒数
    if val >= 86400:
        return f"限时时间：{val // 86400}天"
    if val >= 3600:
        return f"限时时间：{val // 3600}小时"
    if val >= 60:
        return f"限时时间：{val // 60}分钟"
    return f"限时时间：{val}秒"


def _require_lines(item: dict[str, Any]) -> list[str]:
    out: list[str] = []
    req = item.get("Requires")
    if isinstance(req, dict):
        order = ["5", "100", "101", "105", "7", "0"]
        keys = order + [str(k) for k in req.keys() if str(k) not in order]
        seen: set[str] = set()
        for k in keys:
            raw = req.get(k)
            if raw in (None, "") and str(k).isdigit():
                raw = req.get(int(k))
            val = str(raw or "").strip()
            if not val or val in seen:
                continue
            # 过滤无意义的等级 0
            if val in {"需要等级0", "需要等级 0"}:
                continue
            seen.add(val)
            out.append(val)
    rl = item.get("RequireLevel")
    if rl not in (None, "", 0, "0") and not any(str(rl) in x for x in out):
        out.insert(0, f"需要等级{rl}")
    return out


def _attr_color(color_key: Any, text: str = "") -> str:
    key = str(color_key or "white").lower()
    if key == "green":
        return C_GREEN
    if key == "orange":
        return C_ORANGE
    if key == "yellow":
        return C_YELLOW
    if "font=101" in text.lower() or text.startswith("装备："):
        return C_ORANGE
    return C_WHITE


def _desc_segments(desc_raw: Any) -> list[tuple[str, str]]:
    segs = _rich_segments(desc_raw, default_color=C_DESC)
    fixed: list[tuple[str, str]] = []
    for text, color in segs:
        if text.startswith("使用"):
            fixed.append((text, C_GREEN))
        elif color == C_WHITE:
            fixed.append((text, C_DESC))
        else:
            fixed.append((text, color))
    return fixed


def _set_lines(item: dict[str, Any]) -> list[tuple[str, str]]:
    st = item.get("Set")
    if not isinstance(st, dict):
        return []
    rows: list[tuple[str, str]] = []
    name = str(st.get("name") or "").strip()
    siblings = st.get("siblings") or []
    attrs = st.get("attributes") or {}
    if name:
        n = len(siblings) if isinstance(siblings, list) and siblings else 0
        title = f"{name}(1/{n})" if n else name
        rows.append((title, C_YELLOW))
    if isinstance(siblings, list):
        for sib in siblings:
            text = str(sib or "").strip()
            if not text:
                continue
            # 官网套装部件用紧凑斜杠，不额外加空格
            rows.append((text, C_WHITE))
    if isinstance(attrs, dict):
        def _key_num(x: Any) -> tuple[int, str]:
            sx = str(x)
            return (int(sx) if sx.isdigit() else 10**9, sx)

        for k in sorted(attrs.keys(), key=_key_num):
            raw_val = str(attrs.get(k) or "").strip()
            if not raw_val:
                continue
            # 套装属性偶发夹带 Text/font 标签
            segs = _rich_segments(raw_val, default_color=C_GREEN2)
            if segs:
                for text, color in segs:
                    if not text:
                        continue
                    rows.append((f"{k}件：{text}", C_GREEN2 if color in {C_WHITE, C_DESC} else color))
            else:
                val = _plain_text(raw_val)
                if val:
                    rows.append((f"{k}件：{val}", C_GREEN2))
    return rows


def _furniture_lines(item: dict[str, Any]) -> list[tuple[str, str]]:
    fa = item.get("furniture_attributes")
    if not isinstance(fa, dict):
        return []
    rows: list[tuple[str, str]] = []
    record = fa.get("record")
    if record not in (None, ""):
        rows.append((f"装修评分：{record}", C_GREEN))
    return rows



# ---- tip family / slot schema (data/samples/tip_family_slot_schema.json) ----
_TIP_RENDER_ORDER: tuple[str, ...] = (
    "title",
    "strength",
    "usage",
    "bind",
    "exist_time",
    "type_label",
    "furniture_meta",
    "attr_plain",
    "horse_attr_icon",
    "diamonds",
    "requires",
    "durability",
    "set",
    "desc",
    "level",
    "recommend",
    "appearance",
    "cooldown",
    "get_type",
    "get_source",
    "furniture_limit",
    "wucai",
)

_FAMILY_OF_GENRE: dict[str, str] = {
    "1": "weapon",
    "2": "weapon_ranged",
    "3": "equip_armor",
    "4": "equip_trinket",
    "5": "mount",
    "6": "bag",
    "7": "book_secret",
    "8": "recipe",
    "9": "consumable",
    "10": "material",
    "12": "book_read",
    "13": "enhance",
    "14": "guild_product",
    "15": "gem",
    "16": "box",
    "20": "other",
    "21": "furniture",
    "22": "appearance",
    "26": "equip_extended",
    "-1": "quest_item",
    "0": "unknown",
    "99": "other_ext",
    "None": "untyped",
}

_FAMILY_ALIASES: dict[str, str] = {
    "mount_curious": "mount",
    "appearance_or_pet": "appearance",
}

_FAMILY_SLOT_CACHE: dict[str, frozenset[str]] | None = None
_SCHEMA_RENDER_ORDER: tuple[str, ...] | None = None


def _truthy_field(v: Any) -> bool:
    if v is None or v is False:
        return False
    if v == "" or v == [] or v == {} or v == 0 or v == "0":
        return False
    return True


def _genre_key(item: dict[str, Any]) -> str:
    if _truthy_field(item.get("IsQuest")):
        return "-1"
    g = item.get("AucGenre")
    if g is None or g == "" or str(g).lower() == "none":
        return "None"
    return str(g)


def tip_family_of(item: dict[str, Any]) -> str:
    """Map item to tip family id used by tip_family_slot_schema.json."""
    g = _genre_key(item)
    fam = _FAMILY_OF_GENRE.get(g, "other")
    tl = str(item.get("TypeLabel") or "")
    name = str(item.get("Name") or "")
    source = str(item.get("Source") or "").lower()
    st = _subtype_int(item)

    if g == "5":
        if "饰" in tl or "幼崽" in tl:
            return "mount_gear"
        return "mount"
    if g == "22":
        if "挂宠" in name or "挂宠" in tl or "宠物" in tl:
            return "hang_pet"
        if "坐骑" in tl or "奇趣" in name or "奇趣" in tl:
            return "mount"
        return "appearance"
    if g == "4" and any(x in tl for x in ("挂件", "披风")):
        return "appearance_hanger"
    if g == "26":
        try:
            if int(item.get("AucSubType") or -1) == 3:
                return "weapon"
        except Exception:
            pass
        return "equip_extended"
    if isinstance(item.get("furniture_attributes"), dict) or g == "21":
        return "furniture"

    # Heuristics when AucGenre missing / untyped samples
    if name.startswith("挂宠") or tl in {"挂宠", "宠物"} or st == 30:
        return "hang_pet"
    if tl in {"坐骑", "奇趣坐骑"} or name.startswith("坐骑") or st in {15, 25}:
        # SubType 15 appears on some mount-body tips from API
        if source in {"weapon", "armor"}:
            pass
        else:
            if "饰" in tl:
                return "mount_gear"
            return "mount"
    if source == "weapon" or fam == "weapon":
        return "weapon"
    if source == "armor":
        return "equip_armor"
    if source == "homeland":
        return "furniture"

    return _FAMILY_ALIASES.get(fam, fam)


def _load_family_slot_map() -> dict[str, frozenset[str]]:
    global _FAMILY_SLOT_CACHE, _SCHEMA_RENDER_ORDER
    if _FAMILY_SLOT_CACHE is not None:
        return _FAMILY_SLOT_CACHE

    path = Path(__file__).resolve().parent / "assets" / "tip_templates" / "family_slot_schema.json"
    mapping: dict[str, frozenset[str]] = {}
    order = _TIP_RENDER_ORDER
    try:
        import json

        raw = json.loads(path.read_text(encoding="utf-8"))
        ro = raw.get("render_order")
        if isinstance(ro, list) and ro:
            order = tuple(str(x) for x in ro)
        families = raw.get("families") or {}
        if isinstance(families, dict):
            for fk, fam in families.items():
                slots = fam.get("slots") if isinstance(fam, dict) else None
                ids: list[str] = []
                if isinstance(slots, list):
                    for s in slots:
                        if isinstance(s, dict) and s.get("id"):
                            ids.append(str(s["id"]))
                        elif isinstance(s, str):
                            ids.append(s)
                # title is always available
                if "title" not in ids:
                    ids.insert(0, "title")
                mapping[str(fk)] = frozenset(ids)
    except Exception:
        mapping = {}

    _SCHEMA_RENDER_ORDER = order
    _FAMILY_SLOT_CACHE = mapping
    return mapping


def _slots_for_family(family: str) -> frozenset[str]:
    mapping = _load_family_slot_map()
    fam = _FAMILY_ALIASES.get(family, family)
    if fam in mapping:
        return mapping[fam]
    # Unknown family: allow full official order, still omit empty at emit time.
    return frozenset(_SCHEMA_RENDER_ORDER or _TIP_RENDER_ORDER)


def _slot_allowed(allowed: frozenset[str], slot: str) -> bool:
    return slot in allowed


def _get_source_lines(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Build GetSource tree rows only (no GetType fallback)."""
    rows: list[dict[str, Any]] = []
    src = item.get("GetSource")
    if not (isinstance(src, list) and src):
        return rows

    body_rows: list[dict[str, Any]] = []
    for block in src:
        if isinstance(block, dict):
            label = str(block.get("label") or "").strip()
            children = block.get("children") or []
            if label:
                # Group labels (物品/商店/...) sit one indent in, not flush with title
                body_rows.append({"text": label, "color": C_WHITE, "kind": "source_group"})
            for ch in children:
                if isinstance(ch, dict):
                    name = str(ch.get("label") or ch.get("Name") or "").strip()
                    if not name:
                        continue
                    app = str(ch.get("app") or "").strip().lower()
                    # Official: item leaves use quality color + [] + arrow
                    if app == "item":
                        try:
                            q = int(ch.get("quality") or 0)
                        except Exception:
                            q = 0
                        color = QUALITY_COLORS.get(q, C_SOURCE_LEAF)
                        leaf = name if (name.startswith("[") and name.endswith("]")) else f"[{name}]"
                        body_rows.append({"text": leaf, "color": color, "kind": "source_leaf", "arrow": True})
                    else:
                        # reputation/adventure/achievement etc: green + [] + arrow
                        leaf = name if (name.startswith("[") and name.endswith("]")) else f"[{name}]"
                        body_rows.append({"text": leaf, "color": C_SOURCE_LEAF, "kind": "source_leaf", "arrow": True})
                else:
                    leaf = str(ch or "").strip()
                    if not leaf:
                        continue
                    # shop/NPC string leaves: green + [] + arrow
                    if not (leaf.startswith("[") and leaf.endswith("]")):
                        leaf = f"[{leaf}]"
                    body_rows.append({"text": leaf, "color": C_SOURCE_LEAF, "kind": "source_leaf", "arrow": True})
        else:
            plain = str(block or "").strip()
            if plain:
                # bare group without children still indented
                body_rows.append({"text": plain, "color": C_WHITE, "kind": "source_group"})
    if not body_rows:
        return rows
    rows.append({"text": "获取途径:", "color": C_SOURCE_HEADER, "kind": "normal"})
    rows.extend(body_rows)
    return rows


def _get_type_row(
    item: dict[str, Any],
    *,
    allow_with_source: bool = False,
) -> dict[str, Any] | None:
    """Single 物品来源 line, optionally when GetSource exists but is gated."""
    if not allow_with_source and isinstance(item.get("GetSource"), list) and item.get("GetSource"):
        return None
    get_type = str(item.get("GetType") or "").strip()
    if not get_type:
        return None
    text_gt = get_type if get_type.startswith("物品来源") else f"物品来源：{get_type}"
    return {"text": text_gt, "color": C_WHITE, "kind": "normal", "slot": "get_type"}



def _is_weapon(item: dict[str, Any]) -> bool:
    source = str(item.get("Source") or "").strip().lower()
    if source == "weapon":
        return True
    try:
        g = int(item.get("AucGenre"))
        if g == 1:
            return True
        # 奇境武器等
        if g == 26 and int(item.get("AucSubType") or -1) == 3:
            return True
    except Exception:
        pass
    type_label = _type_label(item)
    if type_label.endswith("类"):
        return True
    weapon_labels = {
        "兵刃",
        "重剑",
        "轻剑",
        "长兵",
        "短兵",
        "暗器",
        "弓弩",
        "盾刀",
        "链刃",
        "弯刀",
        "笔",
        "笔类",
        "百草卷",
        "伞",
        "双刀",
        "傲霜刀",
        "千机匣",
        "虫笛类",
        "横刀",
        "弓箭",
        "扇",
        "魂灯",
        "琴",
        "棒",
    }
    return type_label in weapon_labels


def _horse_attr_parts(raw_label: str) -> tuple[str, str]:
    """Split horse skill HTML into green title + white body description."""
    s = str(raw_label or "").strip()
    if not s:
        return "", ""

    title = ""
    body = ""
    m_title = re.search(r"<span\b[^>]*>(.*?)</span>", s, flags=re.I | re.S)
    if m_title:
        title = _plain_text(m_title.group(1)).strip()
    bodies = re.findall(r"<div\b[^>]*>(.*?)</div>", s, flags=re.I | re.S)
    if bodies:
        body = "\n".join(part for part in (_plain_text(b).strip() for b in bodies) if part)
    if not title and not body:
        plain = _plain_text(s).strip()
        if "\n" in plain:
            title, body = plain.split("\n", 1)
            title, body = title.strip(), body.strip()
        else:
            title = plain
    elif not title:
        # icon row without green span: keep first line as title
        plain = _plain_text(s).strip()
        title = plain.split("\n", 1)[0].strip() if plain else ""
        if body and title == body:
            body = ""
    return title, body


def _attr_rows(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Build attribute rows; horse skill lines with icon_id become horse_attr."""
    attrs = item.get("attributes") or []
    if not isinstance(attrs, list):
        return []

    speed_text = ""
    rows: list[dict[str, Any]] = []
    for attr in attrs:
        if not isinstance(attr, dict):
            continue
        raw_label = str(attr.get("label") or "").strip()
        if not raw_label:
            continue

        plain_probe = _plain_text(raw_label)
        if plain_probe.startswith("速度") and "武器伤害" not in plain_probe:
            speed_text = plain_probe
            continue

        icon_raw = attr.get("icon_id")
        icon_id = str(icon_raw).strip() if icon_raw not in (None, "", "None", 0, "0") else ""
        if icon_id:
            title, body = _horse_attr_parts(raw_label)
            if not title and not body:
                continue
            rows.append(
                {
                    "text": title or body,
                    "color": C_GREEN,
                    "kind": "horse_attr",
                    "title": title or body,
                    "body": body if title else "",
                    "icon_id": icon_id,
                    "icon_url": ICON.format(icon_id=icon_id),
                }
            )
            continue

        segs = _rich_segments(raw_label, default_color=_attr_color(attr.get("color"), raw_label))
        if not segs:
            continue
        for text, color in segs:
            base = _attr_color(attr.get("color"), text)
            if color in {C_GREEN, C_ORANGE, C_YELLOW}:
                final_color = color
            elif base != C_WHITE:
                final_color = base
            else:
                final_color = color if color != C_DESC else C_WHITE
            rows.append({"text": text, "color": final_color, "kind": "attr"})

    if rows and speed_text:
        # Official tip places weapon speed on the first plain attr row.
        for row in rows:
            if row.get("kind") == "attr":
                row["right"] = speed_text
                row["right_color"] = C_WHITE
                break
        else:
            rows.insert(0, {"text": speed_text, "color": C_WHITE, "kind": "attr"})
    elif speed_text:
        rows.append({"text": speed_text, "color": C_WHITE, "kind": "attr"})
    return rows


def _build_rows(item: dict[str, Any]) -> list[dict[str, Any]]:
    """统一按 family 槽位表生成 tip 行：有值才出，无值省略。"""
    family = tip_family_of(item)
    allowed = _slots_for_family(family)
    rows: list[dict[str, Any]] = []

    name = str(item.get("Name") or "未知物品")
    try:
        quality = int(item.get("Quality") or 0)
    except Exception:
        quality = 0
    qcolor = QUALITY_COLORS.get(quality, C_WHITE)

    # title (+ optional strength on the right)
    strength = ""
    if _slot_allowed(allowed, "strength"):
        max_strength = _max_strength_value(item)
        if max_strength is not None:
            strength = f"精炼等级：0 / {max_strength}"
    rows.append(
        {
            "text": name,
            "color": qcolor,
            "kind": "title",
            "right": strength,
            "right_color": C_STRENGTH,
            "slot": "title",
            "family": family,
        }
    )

    if _slot_allowed(allowed, "usage"):
        usage = _usage_text(item)
        if usage:
            rows.append(
                {
                    "text": usage,
                    "color": C_WHITE,
                    "kind": "usage",
                    "icon_key": item.get("EquipUsage"),
                    "slot": "usage",
                }
            )

    if _slot_allowed(allowed, "bind"):
        bind = _bind_text(item)
        if bind:
            rows.append({"text": bind, "color": C_WHITE, "kind": "normal", "slot": "bind"})

    if _slot_allowed(allowed, "exist_time"):
        exist_t = _exist_time_text(item.get("MaxExistTime"))
        if exist_t:
            rows.append({"text": exist_t, "color": C_EXIST, "kind": "normal", "slot": "exist_time"})

    if _slot_allowed(allowed, "type_label"):
        type_label = _type_label(item)
        if _is_weapon(item):
            right = type_label if type_label and type_label != "武器" else ""
            rows.append(
                {
                    "text": "武器",
                    "color": C_WHITE,
                    "kind": "normal",
                    "right": right,
                    "right_color": C_WHITE,
                    "slot": "type_label",
                }
            )
        elif type_label and type_label not in _HIDE_TYPE_LABELS:
            # 官网挂宠/坐骑/挂件 tip 常不展示 u-type-label
            rows.append({"text": type_label, "color": C_WHITE, "kind": "normal", "slot": "type_label"})

    if _slot_allowed(allowed, "furniture_meta"):
        for text_f, color in _furniture_lines(item):
            rows.append({"text": text_f, "color": color, "kind": "normal", "slot": "furniture_meta"})

    # attributes: plain vs horse icon rows share one pass, then gate by slot
    if _slot_allowed(allowed, "attr_plain") or _slot_allowed(allowed, "horse_attr_icon"):
        for attr_row in _attr_rows(item):
            kind = str(attr_row.get("kind") or "attr")
            if kind == "horse_attr":
                if _slot_allowed(allowed, "horse_attr_icon"):
                    attr_row = dict(attr_row)
                    attr_row["slot"] = "horse_attr_icon"
                    rows.append(attr_row)
            else:
                if _slot_allowed(allowed, "attr_plain"):
                    attr_row = dict(attr_row)
                    attr_row["slot"] = "attr_plain"
                    rows.append(attr_row)

    if _slot_allowed(allowed, "diamonds"):
        diamonds = item.get("Diamonds") or []
        for d in diamonds:
            text_d = str(d or "").strip()
            if not text_d:
                continue
            if not text_d.startswith("镶嵌孔"):
                text_d = f"镶嵌孔：{text_d}"
            rows.append({"text": text_d, "color": C_GRAY, "kind": "diamond", "slot": "diamonds"})
        if diamonds and _is_weapon(item):
            rows.append({"text": "<只能镶嵌五彩石>", "color": C_GRAY, "kind": "normal", "slot": "diamonds"})

    if _slot_allowed(allowed, "requires"):
        for req in _require_lines(item):
            rows.append({"text": req, "color": C_WHITE, "kind": "normal", "slot": "requires"})

    if _slot_allowed(allowed, "durability"):
        max_dur = item.get("MaxDurability")
        if is_true_equip(item) and max_dur not in (None, "", 0, "0"):
            rows.append(
                {
                    "text": f"最大耐久度{max_dur}",
                    "color": C_WHITE,
                    "kind": "normal",
                    "slot": "durability",
                }
            )

    set_lines = _set_lines(item) if _slot_allowed(allowed, "set") else []
    if set_lines:
        rows.append({"text": "", "color": C_WHITE, "kind": "spacer", "slot": "set"})
        for text_s, color in set_lines:
            rows.append({"text": text_s, "color": color, "kind": "normal", "slot": "set"})
        rows.append({"text": "", "color": C_WHITE, "kind": "spacer", "slot": "set"})

    desc_segs = _desc_segments(item.get("Desc")) if _slot_allowed(allowed, "desc") else []
    if desc_segs:
        if not set_lines:
            rows.append({"text": "", "color": C_WHITE, "kind": "spacer", "slot": "desc"})
        for text_d, color in desc_segs:
            rows.append({"text": text_d, "color": color, "kind": "desc", "slot": "desc"})
        rows.append({"text": "", "color": C_WHITE, "kind": "spacer", "slot": "desc"})

    if _slot_allowed(allowed, "level"):
        level = item.get("Level")
        if level not in (None, ""):
            rows.append({"text": f"品质等级{level}", "color": C_YELLOW, "kind": "normal", "slot": "level"})

    if _slot_allowed(allowed, "recommend"):
        recommend = str(item.get("Recommend") or "").strip()
        if recommend:
            rows.append(
                {
                    "text": f"推荐门派：{recommend}",
                    "color": C_WHITE,
                    "kind": "normal",
                    "slot": "recommend",
                }
            )

    if _slot_allowed(allowed, "appearance"):
        appearance = str(item.get("Appearance") or "").strip()
        if appearance:
            rows.append(
                {
                    "text": f"外观名称：{appearance}",
                    "color": C_WHITE,
                    "kind": "normal",
                    "slot": "appearance",
                }
            )
        exterior = str(item.get("CanExterior") or "").strip()
        if exterior and exterior not in ("True", "False", "true", "false"):
            if not exterior.startswith("外观"):
                exterior = f"外观：{exterior}"
            rows.append({"text": exterior, "color": C_WHITE, "kind": "normal", "slot": "appearance"})

    if _slot_allowed(allowed, "cooldown"):
        cool = _cooldown_text(item.get("CoolDown"))
        if cool:
            rows.append({"text": cool, "color": C_WHITE, "kind": "normal", "slot": "cooldown"})

    # get_source tree preferred; else get_type fallback — each gated independently
    tree_rows = _get_source_lines(item)
    if tree_rows and _slot_allowed(allowed, "get_source"):
        for src_row in tree_rows:
            src_row = dict(src_row)
            src_row.setdefault("slot", "get_source")
            rows.append(src_row)
    elif _slot_allowed(allowed, "get_type"):
        # Reaching this branch means no source tree was actually rendered.
        gt = _get_type_row(item, allow_with_source=True)
        if gt:
            rows.append(gt)

    if _slot_allowed(allowed, "furniture_limit"):
        fa = item.get("furniture_attributes")
        if isinstance(fa, dict) and fa.get("limit") not in (None, ""):
            rows.append(
                {
                    "text": f"摆放上限：{fa.get('limit')}",
                    "color": C_WHITE,
                    "kind": "normal",
                    "slot": "furniture_limit",
                }
            )

    if _slot_allowed(allowed, "wucai"):
        wucai = item.get("WuCaiHtml") or item.get("WuCai") or ""
        wucai_s = str(wucai or "").strip()
        if wucai_s:
            for text_w, color in _rich_segments(wucai_s, default_color=C_GREEN):
                if text_w:
                    rows.append({"text": text_w, "color": color, "kind": "normal", "slot": "wucai"})

    return rows



def render_item_tip(item: dict[str, Any], icon_bytes: bytes | None, out_path: str | Path) -> str:
    """本地复刻官网 tip。

    icon_bytes 保留兼容参数；官网 tip 主体不放左侧大图标，因此默认不绘制。
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    is_equip = is_true_equip(item)
    type_label_probe = _type_label(item)
    is_furniture_probe = bool(item.get("furniture_attributes")) or str(item.get("Source") or "").lower() == "homeland" or type_label_probe in {
        "家具",
        "景观",
        "收集",
        "建筑",
    }
    if is_equip or _is_weapon(item):
        content_w = 320
    elif is_furniture_probe:
        content_w = 320
    else:
        content_w = 250
    pad_x = 12
    # 对照官方 tip：普通装备 21；含套装的复杂 tip 略加大行距
    has_set = isinstance(item.get("Set"), dict) and bool(item.get("Set"))
    if is_equip or _is_weapon(item):
        # 含套装的复杂 tip 行距略大，贴合官网高度
        pad_y, line_h = (11, 22) if has_set else (11, 21)
    elif is_furniture_probe:
        pad_y, line_h = 10, 20
    else:
        pad_y, line_h = 8, 18

    # 装备 tip 14px；短 tip 略小以贴近官网宽度
    font = get_font(14 if (is_equip or _is_weapon(item) or is_furniture_probe) else 13)
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8), (0, 0, 0, 0)))

    raw_rows = _build_rows(item)

    # 先按未换行文本估宽，避免“先按 250 换行再量宽”导致 tip 过窄
    max_line_w = 0
    for row in raw_rows:
        kind = row.get("kind")
        text = str(row.get("text") or "")
        extra = 18 if kind == "diamond" else 0
        if kind == "usage":
            extra += 18
        max_line_w = max(max_line_w, _text_w(probe, text, font) + extra)
        if row.get("right"):
            max_line_w = max(
                max_line_w,
                _text_w(probe, text, font) + _text_w(probe, str(row["right"]), font) + 28,
            )

    type_label = _type_label(item)
    is_furniture = bool(item.get("furniture_attributes")) or str(item.get("Source") or "").lower() == "homeland" or type_label in {
        "家具",
        "景观",
        "收集",
        "建筑",
    }
    if is_equip or _is_weapon(item) or is_furniture:
        width = 341 if (is_equip or _is_weapon(item)) else 345
        content_w = width - pad_x * 2
    else:
        # 消耗/材料等 tip：官网常见最小约 170，长描述可到 320
        width = max(min(max(max_line_w + pad_x * 2 + 6, 170), 320), 170)
        content_w = width - pad_x * 2

    measured: list[dict[str, Any]] = []
    for row in raw_rows:
        kind = row.get("kind")
        if kind in ("title", "spacer", "usage", "diamond"):
            measured.append(row)
            continue

        text = str(row.get("text") or "")
        if text == "" and kind != "spacer":
            measured.append(row)
            continue

        max_w = content_w
        right = str(row.get("right") or "")
        if right:
            max_w = max(content_w - _text_w(probe, right, font) - 18, 80)

        if kind in {"attr", "desc", "normal"}:
            wrapped = _wrap(probe, text, font, max_w) if text else [""]
            if not wrapped:
                measured.append(row)
                continue
            for i, w in enumerate(wrapped):
                nr = dict(row)
                nr["text"] = w
                if i > 0:
                    nr.pop("right", None)
                measured.append(nr)
            continue

        measured.append(row)

    height = pad_y * 2 + 2
    # 官网空白分隔不是整行高；复杂套装 tip 略大一点
    if has_set and (is_equip or _is_weapon(item)):
        spacer_h = 14
    elif is_equip or _is_weapon(item):
        spacer_h = 10
    elif is_furniture:
        spacer_h = 10
    else:
        spacer_h = 8
    for row in measured:
        if row.get("kind") == "spacer":
            height += spacer_h
        else:
            height += line_h
    height = max(height, 80)

    img = Image.new("RGBA", (width, height), C_BG)
    draw = ImageDraw.Draw(img)
    # official panel is near-solid teal; light 1px frame for separation on chat bg
    draw.rectangle((0, 0, width - 1, height - 1), outline=C_BORDER, width=1)

    y = pad_y
    for row in measured:
        kind = row.get("kind")
        text = str(row.get("text") or "")
        color = row.get("color") or C_WHITE

        if kind == "spacer":
            y += spacer_h
            continue

        if kind == "title":
            draw.text((pad_x, y), text, font=font, fill=color)
            right = str(row.get("right") or "")
            if right:
                rw = _text_w(probe, right, font)
                draw.text(
                    (width - pad_x - rw, y),
                    right,
                    font=font,
                    fill=row.get("right_color") or C_STRENGTH,
                )
            y += line_h
            continue

        if kind == "usage":
            x = pad_x
            icon = _load_usage_icon(row.get("icon_key"))
            if icon is not None:
                iy = y + max((line_h - icon.height) // 2, 0)
                img.paste(icon, (x, iy), icon)
                x += icon.width + 4
            draw.text((x, y), text, font=font, fill=color)
            y += line_h
            continue

        if kind == "diamond":
            box = 10
            by = y + max((line_h - box) // 2, 0)
            draw.rectangle((pad_x, by, pad_x + box, by + box), outline=_hex(C_GRAY) + (255,), width=1)
            draw.text((pad_x + box + 5, y), text, font=font, fill=color)
            y += line_h
            continue

        draw.text((pad_x, y), text, font=font, fill=color)
        right = str(row.get("right") or "")
        if right:
            rw = _text_w(probe, right, font)
            draw.text(
                (width - pad_x - rw, y),
                right,
                font=font,
                fill=row.get("right_color") or C_WHITE,
            )
        y += line_h

    _ = icon_bytes
    img.convert("RGB").save(out_path, format="PNG", optimize=True)
    return str(out_path)
