"""Render a clean README screenshot (fake hostname, no LAN IP)."""

import asyncio
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# redact before the app renders anything
socket.gethostname = lambda: "workstation"  # noqa: E731

from cyberdeck import system  # noqa: E402

_real_nics = system.Sampler._nics


def _nics(self):
    nics = _real_nics(self)
    for nic in nics:
        nic.ipv4 = "192.168.1.42"
    return nics


system.Sampler._nics = _nics

from cyberdeck.app import CyberDeck  # noqa: E402

OUT = ROOT / "tools"


async def main() -> None:
    app = CyberDeck()
    async with app.run_test(size=(240, 55)) as pilot:
        await pilot.pause(8.0)
        svg = app.export_screenshot()
        (OUT / "preview.svg").write_text(svg, encoding="utf-8")
        print("hostname redacted:", "DESKTOP-" not in svg.upper())


asyncio.run(main())

import resvg_py  # noqa: E402

FONT = "Consolas" if sys.platform == "win32" else "Menlo" if sys.platform == "darwin" else "DejaVu Sans Mono"
CJK = "Microsoft YaHei" if sys.platform == "win32" else "PingFang SC" if sys.platform == "darwin" else "Noto Sans CJK SC"

svg = (OUT / "preview.svg").read_text(encoding="utf-8")
svg = svg.replace('font-family: "Fira Code";', f'font-family: "{FONT}";')
svg = svg.replace("font-family: Fira Code, monospace;", f"font-family: {FONT}, monospace;")
png = bytes(resvg_py.svg_to_bytes(
    svg, width=1920, monospace_family=FONT, sans_serif_family=CJK,
))
import argparse  # noqa: E402

parser = argparse.ArgumentParser(description="Render the README screenshot")
default_out = "docs/preview-macos.png" if sys.platform == "darwin" else "docs/preview.png"
parser.add_argument("--out", default=default_out, help="output PNG (relative to repo root)")
args = parser.parse_args()
out_path = Path(args.out)
if not out_path.is_absolute():
    out_path = ROOT / out_path
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_bytes(png)
print("wrote", out_path.relative_to(ROOT), len(png), "bytes")
