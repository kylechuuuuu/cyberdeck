"""Modal editor for the custom section: stock symbols and the todo list."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static, TextArea

from . import theme


class EditorScreen(ModalScreen[dict | None]):
    """Returns {"stocks": str, "todo": str, "location": str} on save, None on cancel."""

    BINDINGS = [
        Binding("ctrl+s", "save", "保存"),
        Binding("super+s", "save", "保存", show=False),
        Binding("f2", "save", "保存", show=False),
        Binding("escape", "cancel", "取消"),
    ]

    DEFAULT_CSS = """
    EditorScreen { align: center middle; background: #000000 55%; }
    #dlg { width: 72; height: 26; background: #0b1220; border: round #22d3ee; padding: 1 2; }
    #dlg .field { color: #94a3b8; margin-top: 1; }
    #stocks { border: round #243049; }
    #location { border: round #243049; }
    #todo { height: 8; border: round #243049; }
    #hint { color: #64748b; margin-top: 1; }
    """

    def __init__(self, stocks: list[str], todo_text: str, location: str = "") -> None:
        super().__init__()
        self.stocks = stocks
        self.todo_text = todo_text
        self.location = location

    def compose(self) -> ComposeResult:
        with Vertical(id="dlg"):
            yield Static("股票代码 · 逗号分隔", classes="field")
            yield Input(", ".join(self.stocks), id="stocks", placeholder="sh600519, sz399001, us.AAPL")
            yield Static("定位 · 纬度,经度,城市名（留空＝按时区自动）", classes="field")
            yield Input(self.location, id="location", placeholder="31.2304, 121.4737, Shanghai")
            yield Static("待办 · 每行一条，[x] 已完成", classes="field")
            yield TextArea(self.todo_text, id="todo")
            yield Static("Ctrl+S / F2 保存 · 定位行 Enter 也可 · Esc 取消", id="hint")

    def on_mount(self) -> None:
        p = theme.P
        dialog = self.query_one("#dlg")
        dialog.styles.background = theme.hexc(p.panel)
        dialog.styles.border = ("round", theme.hexc(p.cyan))
        hint = self.query_one("#hint", Static)
        hint.styles.color = theme.hexc(p.dim)
        for label in self.query('.field'):
            label.styles.color = theme.hexc(p.dim)
        self.query_one("#stocks", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Enter in the location field saves: macOS terminals often swallow Ctrl+S
        # for XOFF flow control, so give them a key that always arrives.
        if event.input.id == "location":
            self.action_save()

    def action_save(self) -> None:
        stocks = self.query_one("#stocks", Input).value
        todo = self.query_one("#todo", TextArea).text
        location = self.query_one("#location", Input).value
        self.dismiss({"stocks": stocks, "todo": todo, "location": location})

    def action_cancel(self) -> None:
        self.dismiss(None)

