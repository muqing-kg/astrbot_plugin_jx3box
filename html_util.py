# -*- coding: utf-8 -*-
"""Shared HTML/CSS helpers for tip & quest templates."""
from __future__ import annotations

import re
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


__all__ = ["sanitize_css_color"]
