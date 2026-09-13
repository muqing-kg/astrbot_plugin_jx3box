# -*- coding: utf-8 -*-
"""Shared HTML/CSS helpers for tip & quest templates."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_RGB_RE = re.compile(
    r"^rgb\(\s*(?:25[0-5]|2[0-4]\d|1?\d?\d)\s*,"
    r"\s*(?:25[0-5]|2[0-4]\d|1?\d?\d)\s*,"
    r"\s*(?:25[0-5]|2[0-4]\d|1?\d?\d)\s*\)$"
)
_RGBA_RE = re.compile(
    r"^rgba\(\s*(?:25[0-5]|2[0-4]\d|1?\d?\d)\s*,"
    r"\s*(?:25[0-5]|2[0-4]\d|1?\d?\d)\s*,"
    r"\s*(?:25[0-5]|2[0-4]\d|1?\d?\d)\s*,"
    r"\s*(?:0|0?\.\d+|1(?:\.0+)?)\s*\)$"
)


def sanitize_css_color(value: Any, default: str = "#FFFFFF") -> str:
    """Allow only safe CSS color literals for inline styles."""
    s = str(value or "").strip()
    if not s:
        return default
    if _HEX_RE.match(s) or _RGB_RE.match(s) or _RGBA_RE.match(s):
        return s
    return default


def is_http_url(value: Any) -> bool:
    s = str(value or "").strip().lower()
    return s.startswith("http://") or s.startswith("https://")


def content_width_for_kind(kind: str, tip_width: int | None = None, *, quest: bool = False) -> int:
    """Best-effort content width for t2i viewport (avoid default 800px white band)."""
    if quest:
        return 860
    k = str(kind or "")
    if k in {"equip", "weapon"}:
        return 341
    if k == "furniture":
        return 345
    if tip_width:
        try:
            return max(170, min(320, int(tip_width)))
        except Exception:
            pass
    return 220


def build_t2i_options(
    *,
    width: int,
    height: int = 10,
    base: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Screenshot options for astrbot-t2i / Star.html_render.

    t2i defaults viewport to 800px when unset, which leaves huge white margins
    around narrow tip cards. We pin width to content and omit white page bg.
    """
    w = max(64, int(width or 220))
    h = max(10, int(height or 10))
    opts: dict[str, Any] = {
        "full_page": True,
        "type": "png",
        "omit_background": True,
        "animations": "disabled",
        "caret": "hide",
        "scale": "device",
        "timeout": 30000,
        # Playwright / t2i accepted keys (both snake forms used upstream)
        "viewport": {"width": w, "height": h},
        "viewport_width": w,
        "viewport_height": h,
        "width": w,
        # astrbot-t2i service only honors device_scale_factor_level
        # (normal=1.0 / high=1.3 / ultra=1.8); a raw device_scale_factor key
        # is dropped by its pydantic schema, so text would render at 1x.
        "device_scale_factor_level": "ultra",
    }
    if base:
        opts.update(base)
        # keep size keys authoritative after base merge
        opts["viewport"] = {"width": w, "height": h}
        opts["viewport_width"] = w
        opts["viewport_height"] = h
        opts["width"] = w
    if extra:
        opts.update(extra)
        # if caller overrides width, re-sync viewport aliases
        if "viewport_width" in extra or "width" in extra or "viewport" in extra:
            vw = opts.get("viewport_width") or opts.get("width") or w
            try:
                vw = int(vw)
            except Exception:
                vw = w
            vh = opts.get("viewport_height") or h
            try:
                vh = int(vh)
            except Exception:
                vh = h
            if isinstance(opts.get("viewport"), dict):
                opts["viewport"] = {
                    "width": int(opts["viewport"].get("width") or vw),
                    "height": int(opts["viewport"].get("height") or vh),
                }
            else:
                opts["viewport"] = {"width": vw, "height": vh}
            opts["viewport_width"] = opts["viewport"]["width"]
            opts["viewport_height"] = opts["viewport"]["height"]
            opts["width"] = opts["viewport"]["width"]
    return opts


def crop_render_whitespace(
    image_path: str | Path,
    *,
    bg_threshold: int = 248,
    alpha_threshold: int = 8,
    pad: int = 0,
    dark_panel: bool = False,
) -> str:
    """Crop empty margins from t2i output so card hugs content.

    - Transparent / near-white margins are treated as empty by default.
    - For tip dark panels, also treat pure white page residual as empty, but
      keep dark panel pixels even if semi-transparent over white was flattened.
    """
    from PIL import Image

    path = Path(image_path)
    if not path.is_file():
        return str(path)

    img = Image.open(path).convert("RGBA")
    w, h = img.size
    if w < 8 or h < 8:
        return str(path)
    px = img.load()

    def is_blank(x: int, y: int) -> bool:
        r, g, b, a = px[x, y]
        if a < alpha_threshold:
            return True
        # Tip panels are dark: near-white page residual is empty margin.
        # Quest cards are intentionally white — never treat white fill as empty,
        # only transparent margins (omit_background) are safe to crop.
        if dark_panel and r >= bg_threshold and g >= bg_threshold and b >= bg_threshold:
            return True
        return False

    step_y = max(1, h // 240)
    step_x = max(1, w // 240)

    right = w - 1
    while right > 0:
        if any(not is_blank(right, y) for y in range(0, h, step_y)):
            if any(not is_blank(right, y) for y in range(h)):
                break
        right -= 1

    bottom = h - 1
    while bottom > 0:
        if any(not is_blank(x, bottom) for x in range(0, w, step_x)):
            if any(not is_blank(x, bottom) for x in range(min(w, right + 1))):
                break
        bottom -= 1

    left = 0
    while left < right:
        if any(not is_blank(left, y) for y in range(0, bottom + 1, step_y)):
            if any(not is_blank(left, y) for y in range(bottom + 1)):
                break
        left += 1

    top = 0
    while top < bottom:
        if any(not is_blank(x, top) for x in range(left, right + 1, step_x)):
            if any(not is_blank(x, top) for x in range(left, right + 1)):
                break
        top += 1

    left = max(0, left - pad)
    top = max(0, top - pad)
    right = min(w - 1, right + pad)
    bottom = min(h - 1, bottom + pad)

    new_w = right - left + 1
    new_h = bottom - top + 1
    if new_w < 24 or new_h < 24:
        return str(path)
    # already tight
    if new_w >= w * 0.98 and new_h >= h * 0.98 and left <= 1 and top <= 1:
        return str(path)

    cropped = img.crop((left, top, right + 1, bottom + 1))
    if dark_panel:
        # tip: keep dark look; composite transparent onto tip panel green-black
        bg = Image.new("RGBA", cropped.size, (15, 34, 34, 255))
        bg.paste(cropped, mask=cropped.split()[-1])
        out = bg.convert("RGB")
    else:
        # quest cards are light; flatten onto white
        bg = Image.new("RGB", cropped.size, (255, 255, 255))
        if cropped.mode == "RGBA":
            bg.paste(cropped, mask=cropped.split()[-1])
        else:
            bg.paste(cropped)
        out = bg

    # atomic-ish replace
    tmp = path.with_suffix(path.suffix + ".crop.tmp")
    out.save(tmp, format="PNG", optimize=True)
    tmp.replace(path)
    return str(path)


__all__ = [
    "build_t2i_options",
    "content_width_for_kind",
    "crop_render_whitespace",
    "is_http_url",
    "sanitize_css_color",
]
