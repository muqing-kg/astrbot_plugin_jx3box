"""图片渲染：物品 tip / 任务卡 / 帮助图。"""
from __future__ import annotations

import io
import textwrap
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from .font_util import get_font
from .jx3_api import clean_desc

QUALITY_COLORS = {
    0: "#C8C8C8",
    1: "#FFFFFF",
    2: "#00C848",
    3: "#007EFF",
    4: "#E070FF",
    5: "#FFA500",
}


def _text_w(draw: ImageDraw.ImageDraw, text: str, font) -> int:
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


def render_item_tip(item: dict[str, Any], icon_bytes: bytes | None, out_path: str | Path) -> str:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    name = str(item.get("Name") or "未知物品")
    quality = int(item.get("Quality") or 0)
    qcolor = QUALITY_COLORS.get(quality, "#FFFFFF")
    type_label = str(item.get("TypeLabel") or "")
    auc = item.get("AucGenre")
    weapon_like = isinstance(auc, int) and 1 <= auc <= 4
    desc = clean_desc(item.get("Desc"))
    max_dur = item.get("MaxDurability")
    cool = item.get("CoolDown")
    can_trade = item.get("CanTrade")
    unique = bool(item.get("MaxExistAmount") == 1) or ("唯一" in desc)
    bind_type = item.get("BindType")
    attrs = item.get("attributes") or []

    # 预排版
    font_title = get_font(28, bold=True)
    font_body = get_font(20)
    font_small = get_font(18)
    probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    content_w = 320
    lines: list[tuple[str, object, str]] = []
    lines.append((name, font_title, qcolor))

    tags = []
    if weapon_like:
        tags.append("秘境挑战")
    if can_trade is False or bind_type in (2, 3):
        tags.append("不可交易")
    if unique:
        tags.append("唯一")
    if tags:
        lines.append(("  ".join(tags), font_small, "#D0D0D0"))

    if weapon_like and type_label:
        # 兼容截图：暗器 + 弓弦
        if type_label == "弓弦":
            lines.append(("暗器", font_body, "#C8C8C8"))
        lines.append((type_label, font_body, "#C8C8C8"))
    elif type_label:
        lines.append((type_label, font_body, "#C8C8C8"))

    if max_dur not in (None, ""):
        lines.append((f"最大耐久度{max_dur}", font_body, "#C8C8C8"))

    for attr in attrs[:8]:
        label = str(attr.get("label") or "")
        color = "#00C848" if attr.get("color") == "green" else ("#FFA500" if attr.get("color") == "orange" else "#C8C8C8")
        if label:
            for w in _wrap(probe, label, font_body, content_w):
                lines.append((w, font_body, color))

    if desc:
        # 描述第一行使用色通常偏绿
        desc_lines = _wrap(probe, desc, font_body, content_w)
        for i, w in enumerate(desc_lines[:12]):
            color = "#00C848" if i == 0 and w.startswith("使用") else "#E6D48A"
            lines.append((w, font_body, color))

    if cool not in (None, ""):
        try:
            cool_s = f"使用间隔{int(cool)}秒"
        except Exception:
            cool_s = f"使用间隔{cool}"
        lines.append((cool_s, font_body, "#C8C8C8"))

    # 画布
    pad_x, pad_y = 18, 16
    line_h = 28
    height = pad_y * 2 + 56 + len(lines) * line_h
    width = 360
    img = Image.new("RGBA", (width, max(height, 160)), (18, 20, 24, 245))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, width - 1, img.height - 1), radius=10, outline=(70, 78, 90, 255), width=2)

    # 图标框
    icon = _load_icon(icon_bytes, 48)
    box = (pad_x, pad_y, pad_x + 52, pad_y + 52)
    draw.rectangle(box, outline=(120, 120, 120, 255), width=2)
    img.paste(icon, (pad_x + 2, pad_y + 2), icon)

    y = pad_y
    x_text = pad_x + 64
    for i, (txt, font, color) in enumerate(lines):
        xx = x_text if i == 0 else pad_x
        if i == 0:
            draw.text((xx, y + 8), txt, font=font, fill=color)
            y = pad_y + 56
        else:
            draw.text((xx, y), txt, font=font, fill=color)
            y += line_h

    img.convert("RGB").save(out_path, format="PNG", optimize=True)
    return str(out_path)


def render_quest_card(quest: dict[str, Any], out_path: str | Path) -> str:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    name = str(quest.get("name") or ((quest.get("desc") or {}).get("QuestName")) or "未知任务")
    qid = quest.get("id") or ((quest.get("desc") or {}).get("QuestID")) or ""
    start = quest.get("start") or {}
    end = quest.get("end") or {}
    objective = ((quest.get("desc") or {}).get("Objective")) or ""
    description = clean_desc(((quest.get("desc") or {}).get("Description")) or "")
    # 页面里还有第二段旁白，尽量拼上 FinishedDialogue 作为补充
    finished = clean_desc(((quest.get("desc") or {}).get("FinishedDialogue")) or "")
    if finished and finished not in description:
        description = (description + "\n" + finished).strip()

    chain = ((quest.get("chain") or {}).get("current")) or []
    branch = ((quest.get("chain") or {}).get("branch")) or []
    chain_names = [str(x.get("name")) for x in chain if x.get("visible", True) and x.get("name")]
    branch_names = []
    seen_b = set()
    for x in branch:
        n = str(x.get("name") or "")
        if n and n not in seen_b:
            seen_b.add(n)
            branch_names.append(n)

    start_s = f"{start.get('mapName') or ''} - {start.get('name') or ''}".strip(" -")
    end_s = f"{end.get('mapName') or ''} - {end.get('name') or ''}".strip(" -")
    start_id = start.get("id")
    end_id = end.get("id")

    font_title = get_font(30, bold=True)
    font_h = get_font(22, bold=True)
    font_body = get_font(20)
    font_small = get_font(18)
    probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    max_w = 860

    blocks: list[tuple[str, object, str]] = []
    blocks.append((f"{name}  (ID:{qid})", font_title, "#1F2329"))
    blocks.append((f"任务起点: {start_s}" + (f"  (NPCID: {start_id})" if start_id else ""), font_body, "#8A6D3B"))
    blocks.append((f"任务终点: {end_s}" + (f"  (NPCID: {end_id})" if end_id else ""), font_body, "#8A6D3B"))
    blocks.append(("", font_body, "#000000"))
    blocks.append(("任务目标", font_h, "#333333"))
    for w in _wrap(probe, objective or "无", font_body, max_w):
        blocks.append((w, font_body, "#222222"))
    blocks.append(("", font_body, "#000000"))
    blocks.append(("任务描述", font_h, "#333333"))
    for w in _wrap(probe, description or "无", font_body, max_w):
        blocks.append((w, font_body, "#333333"))
    if chain_names:
        blocks.append(("", font_body, "#000000"))
        blocks.append(("任务链", font_h, "#555555"))
        chain_line = "  »  ".join(f"[{n}]" for n in chain_names)
        for w in _wrap(probe, chain_line, font_body, max_w):
            blocks.append((w, font_body, "#4C6EF5"))
    if branch_names:
        blocks.append(("", font_body, "#000000"))
        blocks.append(("任务分支", font_h, "#555555"))
        branch_line = "  |  ".join(f"[{n}]" for n in branch_names)
        for w in _wrap(probe, branch_line, font_body, max_w):
            blocks.append((w, font_body, "#4C6EF5"))

    pad = 36
    y = pad
    line_gap = 8
    heights = []
    for txt, font, _ in blocks:
        h = 16 if txt == "" else (font.size + 10)
        heights.append(h)
        y += h + line_gap
    width = 960
    height = y + pad
    img = Image.new("RGB", (width, height), "#FFFFFF")
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, width - 1, height - 1), outline="#E5E7EB", width=2)

    y = pad
    for (txt, font, color), h in zip(blocks, heights):
        if txt:
            draw.text((pad, y), txt, font=font, fill=color)
        y += h + line_gap

    img.save(out_path, format="PNG", optimize=True)
    return str(out_path)


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
