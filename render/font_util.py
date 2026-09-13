"""中文字体加载。"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

_PLUGIN_DIR = Path(__file__).resolve().parent.parent


def _candidates(bold: bool = False) -> list[str]:
    names = (
        ["NotoSansSC-Bold.otf", "NotoSansCJKsc-Bold.otf", "msyhbd.ttc"]
        if bold
        else ["NotoSansSC-Regular.otf", "NotoSansCJKsc-Regular.otf", "msyh.ttc"]
    )
    paths: list[str] = []
    for n in names:
        paths.append(str(_PLUGIN_DIR / "fonts" / n))
    if bold:
        paths.extend(
            [
                r"C:\Windows\Fonts\msyhbd.ttc",
                r"C:\Windows\Fonts\msyh.ttc",
                r"C:\Windows\Fonts\simhei.ttf",
            ]
        )
    else:
        paths.extend(
            [
                r"C:\Windows\Fonts\msyh.ttc",
                r"C:\Windows\Fonts\simhei.ttf",
                r"C:\Windows\Fonts\simsun.ttc",
            ]
        )
    return paths


@lru_cache(maxsize=32)
def get_font(size: int = 22, bold: bool = False):
    for path in _candidates(bold=bold):
        if path and os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                continue
    return ImageFont.load_default()
