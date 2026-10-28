"""Textual app: layout, key bindings, theme switching."""

from __future__ import annotations

import argparse
import os
import platform
import socket
from datetime import datetime

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widget import Widget

from . import theme
from .clock import ClockPanel
from .globe import Globe
from .system import SystemPanel
from .weather import WeatherPanel


class TopBar(Widget):
    DEFAULT_CSS = """
    TopBar { height: 1; width: 1fr; background: #0a1122; }
    """

    def on_mount(self) -> None:
        self.set_interval(1.0, self.refresh)

    def render(self) -> Text:
        return topbar_text(self.size.width)


def topbar_text(width: int) -> Text:
    p = theme.P
    t = Text(no_wrap=True, end="")
    title = "▓ CYBERDECK"
    for i, ch in enumerate(title):
        t.append(ch, f"bold {theme.hexc(theme.ramp([p.cyan, p.purple, p.magenta], i / max(1, len(title) - 1)))}")
    t.append("  //  ", theme.hexc(p.dim))
    t.append("TERMINAL OPS", theme.hexc(p.dim))
    right = f"{socket.gethostname().upper()}  ·  {platform.system()}  ·  {datetime.now():%H:%M:%S} "
    pad = max(0, width - len(title) - 18 - len(right))
    t.append(" " * pad, "")
    t.append(right, theme.hexc(theme.mix(p.dim, p.bg, 0.25)))
    return t


class HintBar(Widget):
    DEFAULT_CSS = """
    HintBar { height: 1; width: 1fr; background: #0a1122; }
    """

    def render(self) -> Text:
        return hintbar_text()


def hintbar_text() -> Text:
    p = theme.P
    t = Text(no_wrap=True, end="")
    hints = [
        ("Q", "退出"),
        ("R", "刷新天气"),
        ("SPACE", "暂停自转"),
        ("+/-", "转速"),
        ("T", "配色"),
    ]
    t.append(" ")
    for key, label in hints:
        t.append(f" {key} ", f"bold {theme.hexc(p.bg)} on {theme.hexc(p.cyan)}")
        t.append(f" {label}  ", theme.hexc(p.dim))
    return t


class TooSmalMsg(Widget):
    DEFAULT_CSS = """
    TooSmalMsg { align: center middle; display: none; }
    """

    def render(self) -> Text:
        p = theme.P
        t = Text(justify="center")
        t.append("\n 终端窗口太小\n\n", f"bold {theme.hexc(p.magenta)}")
        t.append("请调整到至少 110 列 × 30 行\n", theme.hexc(p.text))
        t.append(f"当前 {self.app.size.width} × {self.app.size.height}\n", theme.hexc(p.dim))
        return t


class CyberDeck(App):
    CSS = """
    Screen { background: #05080f; overflow: hidden; }
    #body { height: 1fr; overflow: hidden; }
    #left { width: 46%; overflow: hidden; }
    #toprow { height: 16; }
    ClockPanel { width: 32; height: 16; padding: 0 1; }
    WeatherPanel { width: 1fr; height: 16; padding: 0 1; }
    Globe { height: 1fr; }
    #left { border-right: solid #16203a; }
    SystemPanel { padding: 0 1; }
    #toosmall { height: 1fr; width: 1fr; content-align: center middle; background: #05080f; }
    """

    MIN_WIDTH = 110
    MIN_HEIGHT = 30

    BINDINGS = [
        Binding("q", "quit", "退出"),
        Binding("ctrl+c", "quit", "退出", show=False),
        Binding("r", "refresh_weather", "刷新天气"),
        Binding("space", "toggle_spin", "暂停自转"),
        Binding("plus,equal", "faster", "加速"),
        Binding("minus", "slower", "减速"),
        Binding("t", "cycle_theme", "配色"),
    ]

    def __init__(self, city: str | None = None) -> None:
        super().__init__()
        self.city = city
        self.theme_index = 0

    def compose(self) -> ComposeResult:
        yield TopBar()
        with Horizontal(id="body"):
            with Vertical(id="left"):
                with Horizontal(id="toprow"):
                    yield ClockPanel()
                    yield WeatherPanel(city=self.city)
                yield Globe()
            yield SystemPanel()
        yield TooSmalMsg(id="toosmall")
        yield HintBar()

    def on_mount(self) -> None:
        self._apply_theme()
        self._sync_size(self.size)

    def on_resize(self, event) -> None:
        self._sync_size(event.size)

    def _sync_size(self, size) -> None:
        small = size.width < self.MIN_WIDTH or size.height < self.MIN_HEIGHT
        self.query_one("#body").display = not small
        self.query_one(TooSmalMsg).display = small

    def _apply_theme(self) -> None:
        p = theme.P
        self.screen.styles.background = theme.hexc(p.bg)
        for wdg in self.query(TopBar):
            wdg.styles.background = theme.hexc(theme.mix(p.bg, p.cyan, 0.06))
        for wdg in self.query(HintBar):
            wdg.styles.background = theme.hexc(theme.mix(p.bg, p.cyan, 0.06))
        for cls in (ClockPanel, WeatherPanel, SystemPanel):
            for wdg in self.query(cls):
                wdg.styles.background = theme.hexc(p.panel)
        self.query_one("#left").styles.border_right = ("solid", theme.hexc(theme.mix(p.dim, p.bg, 0.35)))
        self.refresh()

    def action_refresh_weather(self) -> None:
        self.query_one(WeatherPanel).refresh_weather()

    def action_toggle_spin(self) -> None:
        self.query_one(Globe).action_toggle_spin()

    def action_faster(self) -> None:
        self.query_one(Globe).action_faster()

    def action_slower(self) -> None:
        self.query_one(Globe).action_slower()

    def action_cycle_theme(self) -> None:
        self.theme_index = (self.theme_index + 1) % len(theme.PALETTES)
        theme.set_palette(self.theme_index)
        self._apply_theme()


def main() -> None:
    parser = argparse.ArgumentParser(prog="cyberdeck", description="Terminal cyberdeck dashboard")
    parser.add_argument("--city", help="wttr.in location, e.g. Hangzhou (default: auto by IP)")
    args = parser.parse_args()
    city = args.city or os.environ.get("CYBERDECK_CITY") or None
    CyberDeck(city=city).run()


if __name__ == "__main__":
    main()
