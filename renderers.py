"""图片渲染：物品 tip / 任务卡 / 帮助图。"""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from .font_util import get_font
from .jx3_api import clean_desc
from .tip_html import render_item_tip as _render_item_tip_impl

# ── 通用颜色 ──────────────────────────────────────────────
QUALITY_COLORS = {
    0: "#A7A7A7",
    1: "#FFFFFF",
    2: "#00D24B",
    3: "#007EFF",
    4: "#FE2DFE",
    5: "#FFA500",
}

# JX3 文本标记颜色（对齐魔盒任务页高亮习惯）
_TAG_COLORS = {
    "G": "#7FDBA8",       # 叙事/NPC 正文绿
    "F171": "#FFD76A",    # 物品
    "F172": "#FF7A6B",    # 怪物/NPC
    "F173": "#6EC8FF",    # 地图
    "F174": "#B7F0B0",    # 动作/旁白
    "N": "#F6D36A",       # 玩家名
    "DEFAULT": "#D7DCE5",
}

_DIFFICULTY_STYLES = {
    "秘境": ("#FF6B6B", "#3A1515"),
    "周常": ("#FFB020", "#3A2610"),
    "日常": ("#56C26A", "#14301A"),
    "活动": ("#C084FC", "#2A1840"),
    "公共": ("#60A5FA", "#15263A"),
    "门派": ("#F59E0B", "#3A2610"),
    "奇遇": ("#F472B6", "#3A1530"),
}

_QUEST_TYPE_LABELS = {
    "common": "普通",
    "repeat": "重复",
    "daily": "日常",
    "week": "周常",
    "adventure": "奇遇",
    "camp": "阵营",
    "school": "门派",
}


# ── Tag 解析 ──────────────────────────────────────────────
_TAG_RE = re.compile(
    r"""
    <CMD\s+NPC_NAME\s+(?P<cmd_npc>[^>]+)>
    | <F(?P<fcode>17[1-4])\s+(?P<ftext>[^>]+)>
    | <(?P<simple>G|N|/G|/N|H28|/H28|H\d+|/H\d+|F17[1-4]|/F17[1-4]|/?[A-Za-z][\w]*)>
    | (?P<text>[^<]+)
    """,
    re.VERBOSE,
)


def parse_tags(raw: str | None) -> list[tuple[str, str]]:
    """将含 JX3 标记的文本解析为 (文本, 颜色) 片段。"""
    if not raw:
        return []
    s = str(raw)
    s = s.replace("\\\\n", "\n").replace("\\n", "\n")
    segments: list[tuple[str, str]] = []
    current = _TAG_COLORS["DEFAULT"]

    for m in _TAG_RE.finditer(s):
        if m.group("cmd_npc") is not None:
            npc = m.group("cmd_npc").strip()
            if npc:
                if segments and not segments[-1][0].endswith("\n"):
                    segments.append(("\n", current))
                segments.append((f"{npc}：", _TAG_COLORS["G"]))
            continue

        if m.group("fcode") is not None:
            key = f"F{m.group('fcode')}"
            color = _TAG_COLORS.get(key, _TAG_COLORS["DEFAULT"])
            text = (m.group("ftext") or "").strip()
            if text:
                segments.append((text, color))
            continue

        simple = m.group("simple")
        if simple is not None:
            tag = simple.upper() if simple in {"g", "n", "G", "N"} else simple
            if tag in {"H28", "H29", "H30"} or tag.startswith("H"):
                if segments and not segments[-1][0].endswith("\n"):
                    segments.append(("\n", current))
                continue
            if tag.startswith("/"):
                current = _TAG_COLORS["DEFAULT"]
                continue
            if tag in _TAG_COLORS:
                current = _TAG_COLORS[tag]
                continue
            # 未知开标签忽略
            continue

        text = m.group("text")
        if text:
            segments.append((text, current))

    return _merge_segments(segments)


def parse_tag_to_plain(raw: str | None) -> str:
    """去除标记，得到纯文本。"""
    if not raw:
        return ""
    parts = [t for t, _ in parse_tags(raw) if t]
    text = "".join(parts)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()




def _normalize_compare_text(text: str) -> str:
    """用于描述/对话去重比较。"""
    s = str(text or "")
    s = re.sub(r"(?m)^[一-鿿A-Za-z0-9_·]{1,12}：", "", s)
    s = re.sub(r"\s+", "", s)
    return s


def _merge_segments(segments: list[tuple[str, str]]) -> list[tuple[str, str]]:
    merged: list[tuple[str, str]] = []
    for text, color in segments:
        if not text:
            continue
        if merged and merged[-1][1] == color:
            merged[-1] = (merged[-1][0] + text, color)
        else:
            merged.append((text, color))
    return merged


# ── 排版工具 ──────────────────────────────────────────────
def _text_w(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    if not text:
        return 0
    box = draw.textbbox((0, 0), text, font=font)
    return max(0, box[2] - box[0])


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    if not text:
        return []
    lines: list[str] = []
    for para in str(text).splitlines() or [""]:
        if not para:
            lines.append("")
            continue
        buf = ""
        for ch in para:
            trial = buf + ch
            if _text_w(draw, trial, font) <= max_w:
                buf = trial
            else:
                if buf:
                    lines.append(buf)
                buf = ch
        if buf:
            lines.append(buf)
    return lines


def _wrap_segments(
    draw: ImageDraw.ImageDraw,
    segments: list[tuple[str, str]],
    font,
    max_w: int,
) -> list[list[tuple[str, str]]]:
    if not segments:
        return []
    result: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    current_w = 0

    def flush() -> None:
        nonlocal current, current_w
        result.append(current or [("", _TAG_COLORS["DEFAULT"])])
        current = []
        current_w = 0

    for text, color in _merge_segments(segments):
        parts = text.split("\n")
        for i, part in enumerate(parts):
            if i > 0:
                flush()
            if not part:
                continue
            buf = ""
            for ch in part:
                trial = buf + ch
                tw = _text_w(draw, trial, font)
                if current_w + tw <= max_w or not buf:
                    buf = trial
                else:
                    if buf:
                        current.append((buf, color))
                        flush()
                    buf = ch
            if buf:
                tw = _text_w(draw, buf, font)
                if current and current_w + tw > max_w:
                    flush()
                current.append((buf, color))
                current_w += tw
    if current:
        result.append(current)
    return result


def _format_money(count: int | float | str | None) -> str:
    try:
        n = int(count or 0)
    except Exception:
        return str(count)
    if n < 0:
        n = 0
    gold, rem = divmod(n, 10000)
    silver, copper = divmod(rem, 100)
    parts: list[str] = []
    if gold:
        parts.append(f"{gold}金")
    if silver:
        parts.append(f"{silver}银")
    if copper or not parts:
        parts.append(f"{copper}铜")
    return "".join(parts)


def _format_rewards(rewards: list[dict[str, Any]] | None) -> list[str]:
    if not rewards:
        return []
    lines: list[str] = []
    for r in rewards:
        if not isinstance(r, dict):
            continue
        t = str(r.get("type") or "")
        c = r.get("count", 0)
        if t == "exp":
            lines.append(f"经验 {c}")
        elif t == "money":
            lines.append(f"金钱 {_format_money(c)}")
        elif t == "tongFund":
            lines.append(f"帮会资金 {c}")
        elif t == "train":
            lines.append(f"修为 {c}")
        elif t == "prestige":
            lines.append(f"声望 {c}")
        elif t == "titlePoint":
            lines.append(f"威望 {c}")
        elif t == "affect":
            force = str(r.get("force") or "势力")
            lines.append(f"{force}声望 {c}")
        elif t == "item_group":
            items = r.get("items") or []
            if not items:
                lines.append("物品奖励")
            else:
                for it in items:
                    amt = it.get("amount", 1)
                    iid = it.get("id") or "?"
                    lines.append(f"物品 x{amt}（{iid}）")
        elif t:
            lines.append(f"{t} {c}")
    return lines


def _get_diff_style(diff: str | None) -> tuple[str, str]:
    if not diff:
        return ("#9CA3AF", "#2A2F3A")
    for key, style in _DIFFICULTY_STYLES.items():
        if key in str(diff):
            return style
    return ("#9CA3AF", "#2A2F3A")


def _load_icon(icon_bytes: bytes | None, size: int = 48) -> Image.Image:
    if icon_bytes:
        try:
            img = Image.open(io.BytesIO(icon_bytes)).convert("RGBA")
            return img.resize((size, size), Image.Resampling.LANCZOS)
        except Exception:
            pass
    img = Image.new("RGBA", (size, size), (50, 50, 50, 255))
    d = ImageDraw.Draw(img)
    d.rectangle((2, 2, size - 3, size - 3), outline=(180, 180, 180, 255), width=2)
    return img


def _extract_dialogues(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        return [text] if text else []
    if isinstance(raw, dict):
        rows = raw.get("dialogues") or []
    elif isinstance(raw, list):
        rows = raw
    else:
        return []
    out: list[str] = []
    for item in rows:
        if isinstance(item, list) and item:
            text = str(item[0] or "").strip()
        elif isinstance(item, str):
            text = item.strip()
        else:
            text = ""
        if text:
            out.append(text)
    return out


# ── 物品 tip ──────────────────────────────────────────────
def render_item_tip(item: dict[str, Any], icon_bytes: bytes | None, out_path: str | Path) -> str:
    """Item tip via HTML multi-template (AstrBot html_render / t2i)."""
    return _render_item_tip_impl(item, icon_bytes, out_path)


def render_quest_card(quest: dict[str, Any], out_path: str | Path) -> str:
    """渲染任务信息卡（深色魔盒风格，带标签色与分段）。"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    desc = quest.get("desc") or {}
    if not isinstance(desc, dict):
        desc = {}

    qid = quest.get("id") or desc.get("QuestID") or ""
    name = str(quest.get("name") or desc.get("QuestName") or "未知任务")
    difficulty = quest.get("difficulty") or desc.get("Difficulty") or ""
    difficulty = str(difficulty).strip() if difficulty not in (None, "") else ""

    start = quest.get("start") or {}
    end = quest.get("end") or {}
    start_map = str(start.get("mapName") or "").strip()
    start_npc = str(start.get("name") or "").strip()
    end_map = str(end.get("mapName") or "").strip()
    end_npc = str(end.get("name") or "").strip()
    start_id = start.get("id")
    end_id = end.get("id")

    objective_raw = desc.get("Objective") or ""
    description_raw = desc.get("Description") or ""
    finished_raw = desc.get("FinishedDialogue") or ""

    accept_dialogues = _extract_dialogues(desc.get("AcceptRpgID"))
    finish_dialogues = _extract_dialogues(desc.get("FinishRpgID"))
    if not finish_dialogues and finished_raw:
        finish_dialogues = [str(finished_raw)]

    rewards = quest.get("rewards") or []
    reward_lines = _format_rewards(rewards if isinstance(rewards, list) else [])
    need_items = quest.get("needItems") or []
    kill_npcs = quest.get("killNpcs") or []
    offer_items = quest.get("offerItems") or []

    chain = ((quest.get("chain") or {}).get("current")) or []
    chain_names = [str(x.get("name")) for x in chain if x.get("visible", True) and x.get("name")]
    branch = ((quest.get("chain") or {}).get("branch")) or []
    branch_names: list[str] = []
    seen_b: set[str] = set()
    for x in branch:
        n = str(x.get("name") or "").strip()
        if n and n not in seen_b:
            seen_b.add(n)
            branch_names.append(n)

    quest_type = str(quest.get("questType") or "").strip()
    school_name = str(quest.get("schoolName") or "").strip()
    type_tags: list[str] = []
    type_label = _QUEST_TYPE_LABELS.get(quest_type, quest_type)
    if type_label:
        type_tags.append(type_label)
    if school_name:
        type_tags.append(school_name)
    if quest.get("canShare"):
        type_tags.append("可共享")
    if quest.get("canAssist"):
        type_tags.append("可援助")
    # 去重保序
    uniq_tags: list[str] = []
    for t in type_tags:
        if t and t not in uniq_tags:
            uniq_tags.append(t)
    type_tags = uniq_tags

    # 字体
    font_title = get_font(30, bold=True)
    font_h = get_font(22, bold=True)
    font_body = get_font(18)
    font_small = get_font(16)
    font_badge = get_font(15, bold=True)

    # 布局
    width = 860
    pad = 28
    content_w = width - pad * 2

    BG = "#121826"
    BG_CARD = "#182235"
    C_TITLE = "#F4D47A"
    C_BODY = "#D7DCE5"
    C_MUTED = "#8B93A7"
    C_SECTION = "#E0B25A"
    C_LINE = "#2C3850"
    C_REWARD = "#F0C060"
    C_NPC = "#9AD1FF"
    C_TAG_FG = "#F6E7B2"
    C_TAG_BG = "#243047"
    C_TAG_BD = "#4A5D7A"

    probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    blocks: list[tuple[Any, int]] = []

    def lh(font_obj, extra: int = 8) -> int:
        return int(getattr(font_obj, "size", 18)) + extra

    def add_pad(h: int = 8) -> None:
        blocks.append((("pad",), h))

    def add_divider() -> None:
        blocks.append((("divider",), 14))

    def add_section(title: str) -> None:
        blocks.append((("section", title, font_h), lh(font_h, 10)))

    def add_segments(segments: list[tuple[str, str]], font=font_body, max_w: int = content_w, indent: int = 0) -> None:
        if not segments:
            return
        for line in _wrap_segments(probe, segments, font, max(40, max_w - indent)):
            blocks.append((("seg", line, font, indent), lh(font, 7)))

    def add_text(text: str, font=font_body, color: str = C_BODY, indent: int = 0) -> None:
        for line in _wrap(probe, text, font, max(40, content_w - indent)):
            blocks.append((("text", line, font, color, indent), lh(font, 7)))

    # 标题
    blocks.append((("title", name, str(qid), difficulty, font_title, font_badge), lh(font_title, 14)))

    # 标签
    if type_tags:
        blocks.append((("tags", type_tags, font_small), lh(font_small, 12)))

    # NPC
    npc_lines: list[str] = []
    if start_map or start_npc:
        s = " · ".join([x for x in [start_map, start_npc] if x])
        if start_id not in (None, ""):
            s += f"  (NPC {start_id})"
        npc_lines.append(f"接取：{s}")
    if end_map or end_npc:
        s = " · ".join([x for x in [end_map, end_npc] if x])
        if end_id not in (None, ""):
            s += f"  (NPC {end_id})"
        npc_lines.append(f"交付：{s}")
    if npc_lines:
        for line in npc_lines:
            blocks.append((("text", line, font_body, C_NPC, 0), lh(font_body, 6)))

    add_divider()

    # 目标
    obj_segments = parse_tags(objective_raw)
    if obj_segments:
        add_section("任务目标")
        add_segments(obj_segments)
        add_pad(6)

    # 描述 / 对话去重：若描述与接取对话实质相同，只保留描述
    desc_plain = _normalize_compare_text(parse_tag_to_plain(description_raw))
    accept_plain = _normalize_compare_text(parse_tag_to_plain("\n".join(accept_dialogues)))
    same_accept = bool(desc_plain) and bool(accept_plain) and (
        desc_plain == accept_plain
        or desc_plain in accept_plain
        or accept_plain in desc_plain
    )

    desc_segments = parse_tags(description_raw)
    if desc_segments:
        add_section("任务描述")
        add_segments(desc_segments)
        add_pad(6)

    # 接取对话
    if accept_dialogues and not same_accept:
        add_section("接取对话")
        for i, d_text in enumerate(accept_dialogues):
            add_segments(parse_tags(d_text), indent=8)
            if i < len(accept_dialogues) - 1:
                add_pad(4)
        add_pad(6)

    # 交付对话
    if finish_dialogues:
        add_section("交付对话")
        for i, d_text in enumerate(finish_dialogues):
            add_segments(parse_tags(d_text), indent=8)
            if i < len(finish_dialogues) - 1:
                add_pad(4)
        add_pad(6)

    # 所需物品
    if isinstance(need_items, list) and need_items:
        add_section("所需物品")
        for item in need_items:
            if not isinstance(item, dict):
                continue
            need_id = item.get("id") or "?"
            need_amt = item.get("amount", 1)
            drop_from = ""
            for g in item.get("guides") or []:
                if isinstance(g, dict) and g.get("name"):
                    drop_from = f" · 来自 {g.get('name')}"
                    break
            add_text(f"×{need_amt}  {need_id}{drop_from}", color=C_REWARD, indent=8)
        add_pad(6)

    # 给予物品
    if isinstance(offer_items, list) and offer_items:
        add_section("任务发放")
        for item in offer_items:
            if isinstance(item, dict):
                add_text(f"×{item.get('amount', 1)}  {item.get('id') or '?'}", color=C_BODY, indent=8)
            else:
                add_text(str(item), indent=8)
        add_pad(6)

    # 击杀目标
    if isinstance(kill_npcs, list) and kill_npcs:
        add_section("击杀目标")
        for npc in kill_npcs:
            if isinstance(npc, dict):
                n = npc.get("name") or npc.get("id") or "未知"
                amt = npc.get("amount") or npc.get("count") or 1
                add_text(f"{n} ×{amt}", indent=8)
            else:
                add_text(str(npc), indent=8)
        add_pad(6)

    # 奖励
    if reward_lines:
        add_section("任务奖励")
        for line in reward_lines:
            add_text(f"• {line}", color=C_REWARD, indent=8)
        add_pad(6)

    # 任务链
    if len(chain_names) > 1:
        add_section("任务链")
        add_text("  →  ".join(chain_names), color="#8FB5FF")
        add_pad(4)
    if branch_names:
        add_section("任务分支")
        add_text("  |  ".join(branch_names), color="#8FB5FF")

    # 高度
    total_h = pad
    for _, h in blocks:
        total_h += h
    total_h += pad

    img = Image.new("RGBA", (width, max(total_h, 180)), BG)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((6, 6, width - 7, total_h - 7), radius=14, fill=BG_CARD, outline=C_LINE, width=2)

    y = pad
    for block, h in blocks:
        kind = block[0]
        if kind == "pad":
            pass
        elif kind == "divider":
            draw.line([(pad, y + h // 2), (width - pad, y + h // 2)], fill=C_LINE, width=1)
        elif kind == "section":
            title = block[1]
            font = block[2]
            # 左侧小色条
            draw.rounded_rectangle((pad, y + 4, pad + 5, y + font.size + 2), radius=2, fill=C_SECTION)
            draw.text((pad + 12, y), title, font=font, fill=C_SECTION)
        elif kind == "seg":
            segs = block[1]
            font = block[2]
            indent = block[3]
            x = pad + indent
            for txt, clr in segs:
                draw.text((x, y), txt, font=font, fill=clr)
                x += _text_w(draw, txt, font)
        elif kind == "text":
            txt = block[1]
            font = block[2]
            color = block[3]
            indent = block[4]
            draw.text((pad + indent, y), txt, font=font, fill=color)
        elif kind == "tags":
            tags = block[1]
            font = block[2]
            x = pad
            for t in tags:
                tw = _text_w(draw, t, font) + 16
                th = font.size + 8
                draw.rounded_rectangle((x, y, x + tw, y + th), radius=8, fill=C_TAG_BG, outline=C_TAG_BD, width=1)
                draw.text((x + 8, y + 3), t, font=font, fill=C_TAG_FG)
                x += tw + 8
        elif kind == "title":
            _name, _qid, _diff, f_title, f_badge = block[1], block[2], block[3], block[4], block[5]
            x = pad
            if _diff:
                fg, bg = _get_diff_style(_diff)
                badge = str(_diff)
                bw = _text_w(draw, badge, f_badge) + 16
                bh = f_badge.size + 10
                draw.rounded_rectangle((x, y + 6, x + bw, y + 6 + bh), radius=8, fill=bg, outline=fg, width=1)
                draw.text((x + 8, y + 10), badge, font=f_badge, fill=fg)
                x += bw + 12
            draw.text((x, y), _name, font=f_title, fill=C_TITLE)
            if _qid:
                id_x = x + _text_w(draw, _name, f_title) + 12
                # 避免标题过长时 ID 画出边界
                if id_x + 80 < width - pad:
                    draw.text((id_x, y + 8), f"ID:{_qid}", font=get_font(14), fill=C_MUTED)
        y += h

    img.convert("RGB").save(out_path, format="PNG", optimize=True)
    return str(out_path)


# ── 帮助图 ────────────────────────────────────────────────
def render_help_image(out_path: str | Path) -> str:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    font_title = get_font(36, bold=True)
    font_h = get_font(24, bold=True)
    font_body = get_font(22)
    lines = [
        ("剑三查询帮助", font_title, "#1F2329"),
        ("", font_body, "#000"),
        ("物品", font_h, "#0B7285"),
        ("/物品 关键词", font_body, "#222"),
        ("示例：/物品 玄晶", font_body, "#555"),
        ("多个结果时回复 /1 /2 选择", font_body, "#555"),
        ("", font_body, "#000"),
        ("成就", font_h, "#0B7285"),
        ("/成就 关键词", font_body, "#222"),
        ("示例：/成就 武神重临", font_body, "#555"),
        ("返回成就链接", font_body, "#555"),
        ("", font_body, "#000"),
        ("任务", font_h, "#0B7285"),
        ("/任务 关键词", font_body, "#222"),
        ("示例：/任务 茶馆问讯", font_body, "#555"),
        ("返回任务信息卡", font_body, "#555"),
        ("", font_body, "#000"),
        ("提示：查不到会提示名称错误；候选最多 10 条", font_body, "#777"),
    ]
    pad = 40
    width = 720
    height = pad * 2 + len(lines) * 40
    img = Image.new("RGB", (width, height), "#F8FAFC")
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((12, 12, width - 13, height - 13), radius=18, outline="#CBD5E1", width=2)
    y = pad
    for txt, font, color in lines:
        if txt:
            draw.text((pad, y), txt, font=font, fill=color)
        y += 40
    img.save(out_path, format="PNG", optimize=True)
    return str(out_path)
