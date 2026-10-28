"""Textual app: layout, key bindings, theme switching."""

from __future__ import annotations

import argparse
import functools
import os
import platform
import socket
import sys
from datetime import datetime

from rich.cells import cell_len
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widget import Widget

from . import __version__, storage, theme
from .clock import ClockPanel
from .editor import EditorScreen
from .extras import InfoPanel, parse_symbols
from .globe import Globe
from .system import SystemPanel
from .weather import WeatherPanel

HOSTNAME = socket.gethostname().split(".")[0].upper()


@functools.lru_cache(maxsize=1)
def os_label() -> str:
    if sys.platform == "darwin":
        version = platform.mac_ver()[0]
        return f"macOS {version}" if version else "macOS"
    if os.name == "nt":
        return f"Windows {platform.release()}"
    return platform.system()


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
    right = f"{HOSTNAME}  ·  {os_label()}  ·  {datetime.now():%H:%M:%S} "
    pad = max(0, width - len(title) - 18 - len(right))
    t.append(" " * pad, "")
    t.append(right, theme.hexc(theme.mix(p.dim, p.bg, 0.25)))
    return t


class HintBar(Widget):
    DEFAULT_CSS = """
    HintBar { height: 1; width: 1fr; background: #0a1122; }
    """

    def render(self) -> Text:
        return hintbar_text(self.size.width)


def hintbar_text(width: int | None = None) -> Text:
    p = theme.P
    t = Text(no_wrap=True, end="")
    hints = [
        ("Q", "退出"),
        ("R", "天气"),
        ("SPACE", "自转"),
        ("+/-", "转速"),
        ("↑↓", "进程"),
        ("S", "排序"),
        ("K", "结束"),
        ("T", "主题"),
        ("I", "信息栏"),
        ("E", "编辑"),
    ]
    t.append(" ")
    used = 1
    for key, label in hints:
        key_text = f" {key} "
        label_text = f" {label}  "
        chunk = cell_len(key_text) + cell_len(label_text)
        if width is not None and used + chunk > width:
            break
        t.append(key_text, f"bold {theme.hexc(p.bg)} on {theme.hexc(p.cyan)}")
        t.append(label_text, theme.hexc(p.dim))
        used += chunk
    tail = f"· {p.label} "
    if width is None or used + cell_len(tail) <= width:
        t.append("· ", theme.hexc(p.dim))
        t.append(p.label, f"bold {theme.hexc(p.magenta)}")
        t.append(" ", "")
    return t


class TooSmalMsg(Widget):
    DEFAULT_CSS = """
    TooSmalMsg { align: center middle; display: none; }
    """

    def render(self) -> Text:
        p = theme.P
        t = Text(justify="center")
        t.append("\n 终端窗口太小\n\n", f"bold {theme.hexc(p.magenta)}")
        t.append("请调整到至少 110 列 × 30 行（推荐 210 × 55 开信息栏）\n", theme.hexc(p.text))
        t.append(f"当前 {self.app.size.width} × {self.app.size.height}\n", theme.hexc(p.dim))
        return t


class CyberDeck(App):
    CSS = """
    Screen { background: #05080f; overflow: hidden; }
    #body { height: 1fr; overflow: hidden; }
    #left { width: 46%; overflow: hidden; }
    Screen.info #left { width: 40%; }
    #toprow { height: 16; }
    ClockPanel { width: 32; height: 16; padding: 0 1; }
    WeatherPanel { width: 1fr; height: 16; padding: 0 1; }
    Globe { height: 1fr; }
    #left { border-right: solid #16203a; }
    SystemPanel { padding: 0 1; }
    InfoPanel { width: 46; display: none; border-left: solid #16203a; }
    Screen.info InfoPanel { display: block; }
    #toosmall { height: 1fr; width: 1fr; content-align: center middle; background: #05080f; }
    """

    MIN_WIDTH = 110
    MIN_HEIGHT = 30

    BINDINGS = [
        Binding("q", "quit", "退出"),
        Binding("ctrl+c", "quit", "退出", show=False),
        Binding("r", "refresh_weather", "刷新天气"),
        Binding("space", "toggle_spin", "暂停自转"),
        Binding("plus,equal,shift+equal", "faster", "加速"),
        Binding("minus", "slower", "减速"),
        Binding("t", "cycle_theme", "配色"),
        Binding("i", "toggle_info", "信息栏"),
        Binding("e", "edit", "编辑"),
        Binding("1", "theme(0)", "主题1", show=False),
        Binding("2", "theme(1)", "主题2", show=False),
        Binding("3", "theme(2)", "主题3", show=False),
        Binding("4", "theme(3)", "主题4", show=False),
        Binding("5", "theme(4)", "主题5", show=False),
        Binding("6", "theme(5)", "主题6", show=False),
        Binding("7", "theme(6)", "主题7", show=False),
        Binding("8", "theme(7)", "主题8", show=False),
    ]

    def __init__(self, city: str | None = None, fps: int | None = None, paused: bool = False) -> None:
        super().__init__()
        self.title = "CYBERDECK"
        self.config = storage.load_json("config.json") or {}
        self.city = city or self.config.get("city") or None
        try:
            self.fps = max(1, min(30, int(fps if fps is not None else self.config.get("fps", 8))))
        except (TypeError, ValueError):
            self.fps = 8
        self.start_paused = paused
        self.theme_index = theme.palette_index(self.config.get("theme"))
        theme.set_palette(self.theme_index)

    def compose(self) -> ComposeResult:
        yield TopBar()
        with Horizontal(id="body"):
            with Vertical(id="left"):
                with Horizontal(id="toprow"):
                    yield ClockPanel()
                    yield WeatherPanel(city=self.city)
                yield Globe(fps=self.fps, paused=self.start_paused)
            yield SystemPanel()
            yield InfoPanel(self.config)
        yield TooSmalMsg(id="toosmall")
        yield HintBar()

    def on_mount(self) -> None:
        self._apply_theme()
        self._sync_size(self.size)
        self.query_one(SystemPanel).focus()
        self._terminal_hint()

    def _terminal_hint(self) -> None:
        """Apple Terminal has no truecolor; the Earth looks better in modern terminals."""
        if sys.platform != "darwin":
            return
        if os.environ.get("TERM_PROGRAM") != "Apple_Terminal":
            return
        if os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit"):
            return
        self.notify(
            "Apple Terminal 只支持 256 色，地球会丢失部分色彩。推荐 Ghostty / iTerm2 / WezTerm。",
            title="终端配色提示",
            severity="warning",
            timeout=10,
        )

    def on_resize(self, event) -> None:
        self._sync_size(event.size)

    def _sync_size(self, size) -> None:
        small = size.width < self.MIN_WIDTH or size.height < self.MIN_HEIGHT
        self.query_one("#body").display = not small
        self.query_one(TooSmalMsg).display = small
        enabled = bool(self.config.get("info", {}).get("enabled", True))
        self.screen.set_class(size.width >= 210 and enabled, "info")

    def _apply_theme(self) -> None:
        p = theme.P
        self.screen.styles.background = theme.hexc(p.bg)
        for wdg in self.query(TopBar):
            wdg.styles.background = theme.hexc(theme.mix(p.bg, p.cyan, 0.06))
        for wdg in self.query(HintBar):
            wdg.styles.background = theme.hexc(theme.mix(p.bg, p.cyan, 0.06))
        for cls in (ClockPanel, WeatherPanel, SystemPanel, InfoPanel):
            for wdg in self.query(cls):
                wdg.styles.background = theme.hexc(p.panel)
        self.query_one(Globe).refresh()
        self.query_one("#left").styles.border_right = ("solid", theme.hexc(theme.mix(p.dim, p.bg, 0.35)))
        self.refresh()

    def _save_config(self) -> None:
        self.config.update({"theme": theme.P.name, "city": self.city})
        storage.save_json("config.json", self.config)

    def action_refresh_weather(self) -> None:
        self.query_one(WeatherPanel).refresh_weather()

    def action_toggle_spin(self) -> None:
        self.query_one(Globe).action_toggle_spin()

    def action_faster(self) -> None:
        self.query_one(Globe).action_faster()

    def action_slower(self) -> None:
        self.query_one(Globe).action_slower()

    def action_cycle_theme(self) -> None:
        self.action_theme((self.theme_index + 1) % len(theme.PALETTES))

    def action_toggle_info(self) -> None:
        info = self.config.setdefault("info", {})
        info["enabled"] = not bool(info.get("enabled", True))
        self._save_config()
        self._sync_size(self.size)

    def action_edit(self) -> None:
        panel = self.query_one(InfoPanel)
        path = panel._todo_file()
        text = ""
        if path is not None and path.exists():
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
        self.push_screen(EditorScreen(panel.stocks, text), self._apply_edit)

    def _apply_edit(self, result: dict | None) -> None:
        if not result:
            return
        panel = self.query_one(InfoPanel)
        stocks = parse_symbols(result.get("stocks", ""))
        panel.stocks = stocks
        self.config.setdefault("info", {})["stocks"] = stocks
        self._save_config()

        path = panel._todo_file()
        if path is not None:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(result.get("todo", "").rstrip() + "\n", encoding="utf-8")
            except OSError:
                self.notify("待办保存失败", severity="error", timeout=3)
        panel._load_todo()
        panel._poll_stocks()
        panel.refresh()
        self.notify(f"已保存 · 股票 {len(stocks)} 支", timeout=2)

    def action_theme(self, index: int) -> None:
        self.theme_index = int(index) % len(theme.PALETTES)
        theme.set_palette(self.theme_index)
        self._apply_theme()
        self._save_config()
        self.query_one(HintBar).refresh()


def main() -> None:
    parser = argparse.ArgumentParser(prog="cyberdeck", description="Terminal cyberdeck dashboard")
    parser.add_argument("--city", help="wttr.in location, e.g. Hangzhou (default: auto by IP)")
    parser.add_argument("--fps", type=int, help="Earth animation FPS, 1-30 (default: 8, or config.json)")
    parser.add_argument("--still", action="store_true", help="start with the Earth paused (low power)")
    parser.add_argument("--version", action="version", version=f"cyberdeck {__version__}")
    args = parser.parse_args()
    city = args.city or os.environ.get("CYBERDECK_CITY") or None
    CyberDeck(city=city, fps=args.fps, paused=args.still).run()


if __name__ == "__main__":
    main()
