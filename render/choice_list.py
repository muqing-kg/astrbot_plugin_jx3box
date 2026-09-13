# -*- coding: utf-8 -*-
"""Candidate choice list: paging, column layout, text/image helpers."""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter

from .font_util import get_font
from ..api.jx3_api import ICON

PAGE_SIZE = 100
TEXT_THRESHOLD = 10  # 2..10 text; >=11 image

# Adaptive columns by *current page* item count (not total).
_COLUMN_BREAKS = (
    (16, 1),
    (32, 2),
    (60, 3),
    (100, 4),
)

KIND_LABELS = {
    "item": "物品",
    "achievement": "成就",
    "quest": "任务",
}

QUALITY_COLORS = {
    0: "#A7A7A7",
    1: "#FFFFFF",
    2: "#00D24B",
    3: "#007EFF",
    4: "#FE2DFE",
    5: "#FFA500",
}

_ASSETS = Path(__file__).resolve().parent.parent / "assets" / "choice_list"
_BG_CANDIDATES = (
    _ASSETS / "choice_bg.png",
    _ASSETS / "choice_bg.jpg",
)


def choice_columns(count: int) -> int:
    """Return 1..4 columns for a page with `count` entries."""
    n = max(0, int(count or 0))
    if n <= 0:
        return 1
    for upper, cols in _COLUMN_BREAKS:
        if n <= upper:
            return cols
    return 4


def total_pages(total: int, page_size: int = PAGE_SIZE) -> int:
    t = max(0, int(total or 0))
    if t <= 0:
        return 0
    size = max(1, int(page_size or PAGE_SIZE))
    return (t + size - 1) // size


def page_slice(
    rows: list[Any],
    page: int,
    page_size: int = PAGE_SIZE,
) -> tuple[list[Any], int, int]:
    """Return (page_rows, normalized_page, total_pages). page is 1-based."""
    total = len(rows or [])
    pages = total_pages(total, page_size)
    if pages <= 0:
        return [], 1, 0
    p = int(page or 1)
    if p < 1:
        p = 1
    if p > pages:
        p = pages
    size = max(1, int(page_size or PAGE_SIZE))
    start = (p - 1) * size
    return list(rows[start : start + size]), p, pages


def column_major_indices(count: int, columns: int) -> list[list[int]]:
    """Fill top-to-bottom per column, then next column."""
    n = max(0, int(count or 0))
    cols = max(1, int(columns or 1))
    if n <= 0:
        return [[] for _ in range(cols)]
    base, rem = divmod(n, cols)
    heights = [base + (1 if i < rem else 0) for i in range(cols)]
    out: list[list[int]] = []
    idx = 0
    for h in heights:
        out.append(list(range(idx, idx + h)))
        idx += h
    return out


def row_display_name(row: dict[str, Any], name_key: str | None = None) -> str:
    if name_key:
        name = row.get(name_key)
        if name not in (None, ""):
            return str(name)
    return str(row.get("Name") or row.get("name") or row.get("ID") or row.get("id") or "?")


def row_icon_id(row: dict[str, Any]) -> str | None:
    for key in ("IconID", "icon_id", "Icon", "icon"):
        raw = row.get(key)
        if raw in (None, "", "None", 0, "0"):
            continue
        return str(raw).strip()
    return None


def row_quality(row: dict[str, Any]) -> int:
    raw = row.get("Quality")
    if raw in (None, "", "None"):
        return 1
    try:
        return int(raw)
    except Exception:
        return 1


def name_key_for_kind(kind: str) -> str:
    return "name" if kind == "quest" else "Name"


def format_choice_text(rows: list[dict[str, Any]], *, kind_label: str, name_key: str = "Name") -> str:
    """Plain-text candidate list for 2..10 results."""
    lines = [f"找到多个{kind_label}，请直接回复序号："]
    for i, row in enumerate(rows, 1):
        lines.append(f"{i}. {row_display_name(row, name_key)}")
    lines.append("直接回复数字，例如：2")
    return "\n".join(lines)


def choice_header(total: int, kind_label: str, page: int, pages: int) -> str:
    return f"找到 {total} 个{kind_label} · 第 {page}/{pages} 页"


def choice_footer(*, is_last: bool) -> str:
    if is_last:
        return "直接回复数字查看详情 · 已是最后一页"
    return "直接回复数字查看详情 · 回复 换页 下一页"


def _hex_to_rgb(color: str, default: tuple[int, int, int] = (255, 255, 255)) -> tuple[int, int, int]:
    s = str(color or "").strip()
    if s.startswith("#") and len(s) == 7:
        try:
            return int(s[1:3], 16), int(s[3:5], 16), int(s[5:7], 16)
        except Exception:
            return default
    return default


def _placeholder_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (42, 58, 58, 255))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((1, 1, size - 2, size - 2), radius=4, outline=(140, 170, 170, 220), width=1)
    return img


def _load_icon(icon_bytes: bytes | None, size: int) -> Image.Image:
    if icon_bytes:
        try:
            img = Image.open(io.BytesIO(icon_bytes)).convert("RGBA")
            return img.resize((size, size), Image.Resampling.LANCZOS)
        except Exception:
            pass
    return _placeholder_icon(size)


def _make_fallback_bg(width: int, height: int) -> Image.Image:
    """Deep teal panel with soft vignette — readable under white/quality text."""
    base = Image.new("RGB", (width, height), (12, 28, 30))
    px = base.load()
    for y in range(height):
        for x in range(width):
            # subtle vertical gradient + corner darken
            t = y / max(1, height - 1)
            r = int(12 + 10 * (1 - t))
            g = int(28 + 18 * (1 - t))
            b = int(30 + 16 * (1 - t))
            cx = abs(x - width / 2) / (width / 2)
            cy = abs(y - height / 2) / (height / 2)
            vig = 1 - 0.22 * max(cx, cy) ** 2
            px[x, y] = (max(0, int(r * vig)), max(0, int(g * vig)), max(0, int(b * vig)))
    # soft border glow
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle((10, 10, width - 11, height - 11), radius=18, outline=(64, 140, 130, 90), width=2)
    od.rounded_rectangle((18, 18, width - 19, height - 19), radius=14, outline=(30, 70, 68, 50), width=1)
    base = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")
    return base


def _load_background(width: int, height: int) -> Image.Image:
    for path in _BG_CANDIDATES:
        if path.is_file():
            try:
                bg = Image.open(path).convert("RGB")
                bg = bg.resize((width, height), Image.Resampling.LANCZOS)
                # darken slightly for text legibility
                shade = Image.new("RGB", (width, height), (8, 18, 20))
                return Image.blend(bg, shade, 0.35)
            except Exception:
                continue
    return _make_fallback_bg(width, height)


def _truncate_to_width(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> str:
    s = str(text or "")
    if not s:
        return ""
    if draw.textlength(s, font=font) <= max_w:
        return s
    ell = "…"
    while s and draw.textlength(s + ell, font=font) > max_w:
        s = s[:-1]
    return (s + ell) if s else ell


def render_choice_list_image(
    rows: list[dict[str, Any]],
    *,
    kind: str,
    page: int = 1,
    out_path: str | Path,
    icon_bytes_map: dict[str, bytes] | None = None,
    page_size: int = PAGE_SIZE,
) -> str:
    """Render one page of candidate choices as a PNG.

    `rows` is the FULL candidate list; this function slices the requested page.
    Global serial numbers continue across pages.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    kind_label = KIND_LABELS.get(kind, "结果")
    name_key = name_key_for_kind(kind)
    total = len(rows or [])
    page_rows, page_n, pages = page_slice(rows or [], page, page_size=page_size)
    n = len(page_rows)
    cols = choice_columns(n)
    col_groups = column_major_indices(n, cols)
    rows_per_col = max((len(c) for c in col_groups), default=1)

    # Density scales with column count
    if cols == 1:
        canvas_w, icon_size, font_size, row_h, pad_x, gap_x = 720, 28, 22, 40, 36, 18
    elif cols == 2:
        canvas_w, icon_size, font_size, row_h, pad_x, gap_x = 900, 24, 18, 34, 28, 16
    elif cols == 3:
        canvas_w, icon_size, font_size, row_h, pad_x, gap_x = 1080, 22, 16, 30, 24, 12
    else:
        canvas_w, icon_size, font_size, row_h, pad_x, gap_x = 1200, 20, 15, 28, 20, 10

    header_h = 64
    footer_h = 52
    top = 28
    bottom = 24
    content_h = rows_per_col * row_h
    canvas_h = top + header_h + content_h + footer_h + bottom
    # keep a modest minimum height for sparse pages
    canvas_h = max(canvas_h, 220)

    img = _load_background(canvas_w, canvas_h).convert("RGBA")
    # translucent content plate
    plate = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    pd = ImageDraw.Draw(plate)
    pd.rounded_rectangle(
        (14, 14, canvas_w - 15, canvas_h - 15),
        radius=16,
        fill=(10, 24, 26, 170),
        outline=(70, 150, 140, 110),
        width=2,
    )
    img = Image.alpha_composite(img, plate)
    draw = ImageDraw.Draw(img)

    font_header = get_font(26 if cols <= 2 else 22, bold=True)
    font_footer = get_font(16 if cols <= 2 else 14)
    font_idx = get_font(max(13, font_size - 2), bold=True)
    font_name = get_font(font_size)

    header = choice_header(total, kind_label, page_n, max(pages, 1))
    footer = choice_footer(is_last=(pages <= 1 or page_n >= pages))

    # centered header / footer
    hw = draw.textlength(header, font=font_header)
    draw.text(((canvas_w - hw) / 2, top + 8), header, font=font_header, fill=(236, 248, 246, 255))
    fw = draw.textlength(footer, font=font_footer)
    draw.text(
        ((canvas_w - fw) / 2, canvas_h - bottom - footer_h + 14),
        footer,
        font=font_footer,
        fill=(180, 210, 205, 255),
    )

    icons = icon_bytes_map or {}
    content_top = top + header_h
    inner_w = canvas_w - 2 * pad_x
    col_w = (inner_w - gap_x * (cols - 1)) / cols if cols else inner_w
    global_base = (page_n - 1) * max(1, int(page_size or PAGE_SIZE))

    for ci, indices in enumerate(col_groups):
        x0 = pad_x + ci * (col_w + gap_x)
        for ri, local_i in enumerate(indices):
            row = page_rows[local_i]
            serial = global_base + local_i + 1
            y = content_top + ri * row_h
            # index
            idx_s = str(serial)
            idx_w = 42 if cols <= 2 else (36 if cols == 3 else 32)
            draw.text((x0, y + (row_h - font_size) / 2 - 1), idx_s, font=font_idx, fill=(160, 190, 185, 255))
            # icon
            ix = x0 + idx_w
            icon_id = row_icon_id(row)
            raw = icons.get(str(icon_id)) if icon_id else None
            icon = _load_icon(raw, icon_size)
            iy = int(y + (row_h - icon_size) / 2)
            img.paste(icon, (int(ix), iy), icon)
            # name
            q = row_quality(row)
            color = QUALITY_COLORS.get(q, QUALITY_COLORS[1])
            name = row_display_name(row, name_key)
            nx = ix + icon_size + 8
            max_name_w = col_w - (nx - x0) - 4
            name = _truncate_to_width(draw, name, font_name, max_name_w)
            draw.text((nx, y + (row_h - font_size) / 2 - 1), name, font=font_name, fill=color)

    final = img.convert("RGB")
    final.save(out_path, format="PNG", optimize=True)
    return str(out_path)


def icon_url(icon_id: str | int) -> str:
    return ICON.format(icon_id=icon_id)
