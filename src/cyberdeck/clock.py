"""Clock + month calendar panel."""

from __future__ import annotations

import calendar
from datetime import datetime

from rich.text import Text
from textual.widget import Widget

from . import bigfont, theme

WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]
CN_WEEK = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
CN_MONTH = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二"]


class ClockPanel(Widget):
    DEFAULT_CSS = """
    ClockPanel { width: 30; height: 17; }
    """

    def on_mount(self) -> None:
        self.set_interval(0.2, self.refresh)

    # ------------------------------------------------------------------
    def build(self, w: int, h: int) -> Text:
        p = theme.P
        now = datetime.now()
        out = Text(no_wrap=True, end="")

        digits = bigfont.rows(now.strftime("%H:%M"))
        grad = [p.cyan, p.purple, p.magenta]
        for r, row in enumerate(digits):
            color = theme.hexc(theme.ramp(grad, r / max(1, bigfont.HEIGHT - 1)))
            line = Text(no_wrap=True, end="")
            line.append("  ")
            for ch in row:
                line.append("█" if ch == "#" else " ", f"bold {color}")
            out.append_text(line)
            out.append("\n")

        # date line
        out.append("  ")
        out.append(f"{now.month:02d}月{now.day:02d}日", f"bold {theme.hexc(p.text)}")
        out.append("  " + CN_WEEK[now.weekday()], theme.hexc(p.magenta))
        out.append("  " + str(now.year), theme.hexc(p.dim))
        out.append("\n")
        out.append("  " + "─" * max(4, w - 4), theme.hexc(theme.mix(p.dim, p.panel, 0.45)))
        out.append("\n")

        cal = calendar.Calendar(firstweekday=0)
        weeks = cal.monthdayscalendar(now.year, now.month)
        out.append("  ")
        out.append(f"{CN_MONTH[now.month - 1]}月", f"bold {theme.hexc(p.cyan)}")
        out.append(f"  {now.year}", theme.hexc(p.dim))
        out.append("  周" + str(now.isocalendar().week).rjust(2), theme.hexc(p.dim))
        out.append("\n")

        out.append("  ")
        for i, wd in enumerate(WEEKDAYS):
            style = theme.hexc(p.magenta if i >= 5 else p.dim)
            out.append(wd + " ", style)
        out.append("\n")

        for week in weeks:
            out.append("  ")
            for i, day in enumerate(week):
                if day == 0:
                    out.append("   ", theme.hexc(p.dim))
                    continue
                if day == now.day:
                    out.append(f"{day:2d} ", f"bold {theme.hexc(p.bg)} on {theme.hexc(p.cyan)}")
                elif i >= 5:
                    out.append(f"{day:2d} ", theme.hexc(p.magenta))
                else:
                    out.append(f"{day:2d} ", theme.hexc(p.text))
            out.append("\n")
        return out

    def render(self) -> Text:
        w, h = self.content_size
        if w < 10 or h < 4:
            return Text("")
        return self.build(w, h)
