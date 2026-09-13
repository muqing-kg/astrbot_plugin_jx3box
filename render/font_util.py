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


_SIMSUN_PATHS = (
    r"C:\Windows\Fonts\simsun.ttc",
    "/usr/share/fonts/truetype/simsun/simsun.ttc",
    "/usr/share/fonts/simsun.ttc",
    "simsun.ttc",
)


@lru_cache(maxsize=16)
def simsun_embed_css(chars: frozenset) -> str:
    """Subset SimSun to `chars` and return an @font-face CSS block.

    Used so remote t2i servers (no SimSun installed) render the tip with the
    exact game-style serif. Returns "" when the font or fonttools is missing;
    the CSS stack then falls back to a system serif.
    """
    try:
        import base64
        import io

        from fontTools.subset import Options, Subsetter
        from fontTools.ttLib import TTFont
    except Exception:
        return ""

    path = next((p for p in _SIMSUN_PATHS if os.path.exists(p)), "")
    if not path:
        return ""
    try:
        font = TTFont(path, fontNumber=0, lazy=True)
        opts = Options()
        opts.glyph_names = False
        opts.layout_features = []
        subsetter = Subsetter(options=opts)
        subsetter.populate(text="".join(sorted(chars)))
        subsetter.subset(font)
        buf = io.BytesIO()
        font.save(buf)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return (
            "@font-face { font-family: 'JX3SimSun'; "
            f"src: url(data:font/truetype;charset=utf-8;base64,{b64}) format('truetype'); }}"
        )
    except Exception:
        return ""
