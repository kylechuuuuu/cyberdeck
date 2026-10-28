"""Rasterize the dashboard panels to PNG for visual review.

Uses the same build(width, height) methods the widgets use in Textual, and
draws each Rich Text cell with Consolas (+ YaHei for CJK), special-casing
block elements and honouring East Asian double-width characters.
"""

from __future__ import annotations

import sys
import time
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from rich.style import Style
from rich.text import Text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cyberdeck import theme  # noqa: E402
from cyberdeck.app import hintbar_text, topbar_text  # noqa: E402
from cyberdeck.clock import ClockPanel  # noqa: E402
from cyberdeck.globe import GlobeEngine, image_to_text  # noqa: E402
from cyberdeck.system import Sampler, SystemPanel  # noqa: E402
from cyberdeck.weather import WeatherPanel, fetch_weather  # noqa: E402

FONT = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 15)
CJK = ImageFont.truetype("C:/Windows/Fonts/simhei.ttf", 14)
CELL_W, CELL_H = 9, 18


def is_wide(ch: str) -> bool:
    return unicodedata.east_asian_width(ch) in ("W", "F")


def cells(text: Text, w: int, h: int):
    plain = text.plain
    styles: list[Style] = [Style()] * len(plain)
    for span in text.spans:
        st = Style.parse(span.style) if isinstance(span.style, str) else (span.style or Style())
        for i in range(span.start, min(span.end, len(plain))):
            styles[i] = st
    grid = [[(" ", Style()) for _ in range(w)] for _ in range(h)]
    y = x = 0
    for i, ch in enumerate(plain):
        if ch == "\n":
            y += 1
            x = 0
            if y >= h:
                break
            continue
        if y >= h:
            break
        span = 2 if is_wide(ch) else 1
        if x < w:
            grid[y][x] = (ch, styles[i])
            if span == 2 and x + 1 < w:
                grid[y][x + 1] = ("", styles[i])
        x += span
    return grid


def draw_block(draw, x0, y0, text: Text, w: int, h: int, bg: tuple[int, int, int]) -> None:
    grid = cells(text, w, h)
    for y in range(h):
        for x in range(w):
            ch, style = grid[y][x]
            fg = theme.hexc(style.color.get_truecolor()) if style.color else theme.hexc(theme.P.text)
            b = style.bgcolor.get_truecolor() if style.bgcolor else bg
            px, py = x0 + x * CELL_W, y0 + y * CELL_H
            draw.rectangle([px, py, px + CELL_W - 1, py + CELL_H - 1], fill=theme.hexc(b))
            if ch in (" ", ""):
                continue
            wide = is_wide(ch)
            cw = CELL_W * 2 if wide else CELL_W
            if ch == "█":
                draw.rectangle([px, py, px + cw - 1, py + CELL_H - 1], fill=fg)
            elif ch == "▀":
                draw.rectangle([px, py, px + cw - 1, py + CELL_H // 2 - 1], fill=fg)
            elif ch == "▄":
                draw.rectangle([px, py + CELL_H // 2, px + cw - 1, py + CELL_H - 1], fill=fg)
            elif ch in "▁▂▃▄▅▆▇":
                frac = "▁▂▃▄▅▆▇".index(ch) + 1
                hh = CELL_H * frac / 8
                draw.rectangle([px, py + CELL_H - hh, px + CELL_W - 1, py + CELL_H - 1], fill=fg)
            elif ch in "░▒▓":
                a = {"░": 0.32, "▒": 0.55, "▓": 0.8}[ch]
                fg_rgb = tuple(int(fg[i:i + 2], 16) for i in (1, 3, 5))
                blend = tuple(int(b[i] + (fg_rgb[i] - b[i]) * a) for i in range(3))
                draw.rectangle([px, py, px + CELL_W - 1, py + CELL_H - 1], fill=theme.hexc(blend))
            elif ch == "─":
                draw.line([px, py + CELL_H // 2, px + CELL_W - 1, py + CELL_H // 2], fill=fg)
            elif ch == "●":
                draw.ellipse([px + 2, py + 6, px + CELL_W - 3, py + CELL_H - 6], fill=fg)
            elif ch == "·":
                draw.ellipse([px + 3, py + 8, px + 5, py + 10], fill=fg)
            else:
                draw.text((px, py + 1), ch, font=CJK if wide else FONT, fill=fg)


def main() -> None:
    theme.set_palette(0)
    P = theme.P

    total_w, total_h = 160, 44
    left_w = int(total_w * 0.46)
    top_h = 16
    globe_w = left_w - 1
    globe_h = total_h - 2 - top_h
    sys_w = total_w - left_w - 2

    canvas = Image.new("RGB", (total_w * CELL_W, total_h * CELL_H), theme.hexc(P.bg))
    draw = ImageDraw.Draw(canvas)

    draw_block(draw, 0, 0, topbar_text(total_w), total_w, 1, theme.mix(P.bg, P.cyan, 0.06))
    draw_block(draw, 0, (total_h - 1) * CELL_H, hintbar_text(), total_w, 1, theme.mix(P.bg, P.cyan, 0.06))

    # left card background + divider
    cy = CELL_H
    draw.rectangle([0, cy, left_w * CELL_W - 1, cy + top_h * CELL_H - 1], fill=theme.hexc(P.panel))
    draw.line([left_w * CELL_W - 1, 0, left_w * CELL_W - 1, (total_h - 1) * CELL_H],
              fill=theme.hexc(theme.mix(P.dim, P.bg, 0.35)))
    draw_block(draw, CELL_W, cy, ClockPanel().build(30, top_h), 30, top_h, P.panel)

    weather = WeatherPanel()
    weather.data = fetch_weather(None)
    if weather.data:
        print("weather:", weather.data.location, weather.data.temp, "°C", len(weather.data.days), "days")
    ww = left_w - 32 - 2
    draw_block(draw, 32 * CELL_W + CELL_W, cy, weather.build(ww, top_h), ww, top_h, P.panel)

    globe = image_to_text(GlobeEngine().render(globe_w, globe_h, -1.2, time.time()),
                          " EARTH · TILT 18.0° · 0.32 rad/s ", hud=["ORBITAL VIEW", "MERIDIAN  68.8°W"])
    draw_block(draw, 0, cy + top_h * CELL_H, globe, globe_w, globe_h, P.panel)

    sampler = Sampler()
    sampler.fast()
    time.sleep(0.8)
    sampler.fast()
    sampler.slow()
    panel = SystemPanel(sampler)
    draw_block(draw, (left_w + 1) * CELL_W, CELL_H, panel.build(sys_w, total_h - 2),
               sys_w, total_h - 2, P.panel)
    print("cpu", sampler.state.cpu, "gpu", sampler.state.gpu)

    out = Path(__file__).parent / "dash_preview.png"
    canvas.save(out)
    print("saved", out, canvas.size)


if __name__ == "__main__":
    main()





