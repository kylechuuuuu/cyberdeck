"""Modal editor for the custom section: stock symbols and the todo list."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static, TextArea

from . import theme


class EditorScreen(ModalScreen[dict | None]):
    """Returns {"stocks": str, "todo": str} on save, None on cancel."""

    BINDINGS = [
        Binding("ctrl+s", "save", "保存"),
        Binding("escape", "cancel", "取消"),
    ]

    DEFAULT_CSS = """
    EditorScreen { align: center middle; background: #000000 55%; }
    #dlg { width: 72; height: 22; background: #0b1220; border: round #22d3ee; padding: 1 2; }
    #dlg Label { color: #94a3b8; margin-top: 1; }
    #stocks { border: round #243049; }
    #todo { height: 9; border: round #243049; }
    #hint { color: #64748b; margin-top: 1; }
    """

    def __init__(self, stocks: list[str], todo_text: str) -> None:
        super().__init__()
        self.stocks = stocks
        self.todo_text = todo_text

    def compose(self) -> ComposeResult:
        with Vertical(id="dlg"):
            yield Label("股票代码 · 逗号分隔")
            yield Input(", ".join(self.stocks), id="stocks", placeholder="sh600519, sz399001, us.AAPL")
            yield Label("待办 · 每行一条，[x] 已完成")
            yield TextArea(self.todo_text, id="todo")
            yield Static("Ctrl+S 保存 · Esc 取消", id="hint")

    def on_mount(self) -> None:
        p = theme.P
        dialog = self.query_one("#dlg")
        dialog.styles.background = theme.hexc(p.panel)
        dialog.styles.border = ("round", theme.hexc(p.cyan))
        hint = self.query_one("#hint", Static)
        hint.styles.color = theme.hexc(p.dim)
        for label in self.query(Label):
            label.styles.color = theme.hexc(p.dim)
        self.query_one("#stocks", Input).focus()

    def action_save(self) -> None:
        stocks = self.query_one("#stocks", Input).value
        todo = self.query_one("#todo", TextArea).text
        self.dismiss({"stocks": stocks, "todo": todo})

    def action_cancel(self) -> None:
        self.dismiss(None)
