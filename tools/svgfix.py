"""Fix Textual's SVG export for CJK.

Textual writes ``textLength = len(run) * cell`` on every text run, so it counts
a Chinese character as one cell. Renderers then squeeze two-cell glyphs into a
single cell and neighbouring characters overlap. This rewrites each run's
``textLength`` to the number of cells it really occupies; the x positions the
layout chose are already correct, only the length attribute is wrong.
"""

from __future__ import annotations

import html
import re
import unicodedata

_TEXT = re.compile(r"<text([^>]*)>(.*?)</text>", re.S)
_ATTR = r'{name}="([\d.]+)"'


def cell_width(text: str) -> int:
    """Terminal cells a string occupies (CJK counts as two)."""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def _attr(attrs: str, name: str) -> float | None:
    match = re.search(_ATTR.format(name=name), attrs)
    return float(match.group(1)) if match else None


def _set_attr(attrs: str, name: str, value: float) -> str:
    return re.sub(_ATTR.format(name=name), f'{name}="{value:.1f}"', attrs, count=1)


def fix_svg_text(svg: str) -> str:
    """Return the SVG with CJK-aware textLength values."""
    matches = list(_TEXT.finditer(svg))
    # a single glyph run (box drawing, letters) is exactly one cell wide
    cell = 0.0
    for match in matches:
        body = html.unescape(re.sub(r"<[^>]+>", "", match.group(2)))
        if len(body) == 1 and cell_width(body) == 1:
            cell = _attr(match.group(1), "textLength") or 0.0
            if cell:
                break
    if not cell:
        return svg

    out: list[str] = []
    pos = 0
    for match in matches:
        attrs, body = match.group(1), match.group(2)
        text = html.unescape(re.sub(r"<[^>]+>", "", body))
        length = _attr(attrs, "textLength")
        wanted = round(cell_width(text) * cell, 1)
        if length is not None and abs(length - wanted) > 0.1:
            attrs = _set_attr(attrs, "textLength", wanted)
            out.append(svg[pos:match.start()])
            out.append(f"<text{attrs}>{body}</text>")
            pos = match.end()
    out.append(svg[pos:])
    return "".join(out)
