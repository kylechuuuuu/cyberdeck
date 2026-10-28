"""Render docs/editor.png: the in-terminal editor modal."""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import resvg_py  # noqa: E402
from svgfix import fix_svg_text  # noqa: E402

from cyberdeck.app import CyberDeck  # noqa: E402

SIZE = (120, 34)
FONT = "Consolas" if sys.platform == "win32" else "Menlo" if sys.platform == "darwin" else "DejaVu Sans Mono"
CJK = ("Microsoft YaHei" if sys.platform == "win32"
       else "PingFang SC" if sys.platform == "darwin" else "Noto Sans CJK SC")


async def capture() -> str:
    app = CyberDeck()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause(4.0)
        await pilot.press("e")
        await pilot.pause(0.8)
        return app.export_screenshot()


svg = asyncio.run(capture())
svg = svg.replace('font-family: "Fira Code";', f'font-family: "{FONT}";')
svg = svg.replace("font-family: Fira Code, monospace;", f"font-family: {FONT}, monospace;")
svg = fix_svg_text(svg)  # Textual counts CJK as one cell; give them two
png = bytes(resvg_py.svg_to_bytes(svg, width=1600, monospace_family=FONT, sans_serif_family=CJK))
(ROOT / "docs" / "editor.png").write_bytes(png)
print("wrote docs/editor.png", len(png), "bytes")
