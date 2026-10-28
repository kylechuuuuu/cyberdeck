"""Headless interaction check: mount, wait for workers, press keys, export SVG."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cyberdeck.app import CyberDeck  # noqa: E402
from cyberdeck.weather import WeatherPanel  # noqa: E402

OUT = Path(__file__).parent / "shot.svg"


async def size_guard() -> None:
    app = CyberDeck()
    async with app.run_test(size=(90, 24)) as pilot:
        await pilot.pause(0.5)
        print("small guard:", app.query_one("#body").display is False,
              app.query_one("TooSmalMsg").display is True)
        from textual.geometry import Size

        app._sync_size(Size(160, 44))
        await pilot.pause(0.3)
        print("restored:", app.query_one("#body").display is True,
              app.query_one("TooSmalMsg").display is False)


async def main() -> None:
    await size_guard()

    app = CyberDeck()
    async with app.run_test(size=(160, 44)) as pilot:
        await pilot.pause(8.0)
        wp = app.query_one(WeatherPanel)
        globe = app.query_one("Globe")
        print("weather loaded:", bool(wp.data), wp.data.location if wp.data else wp.error)
        print("globe size:", globe.size, "yaw:", round(globe.yaw, 2))
        sysp = app.query_one("SystemPanel")
        print("gpu:", sysp.sampler.state.gpu, "procs:", len(sysp.sampler.state.procs))

        OUT.write_text(app.export_screenshot(), encoding="utf-8")
        print("svg saved:", OUT.stat().st_size, "bytes")

        await pilot.press("space")
        await pilot.pause(0.4)
        y1 = globe.yaw
        await pilot.pause(0.6)
        print("paused:", globe.paused, "yaw frozen:", globe.paused and abs(globe.yaw - y1) < 1e-9)
        await pilot.press("plus", "plus", "minus")
        print("speed:", round(globe.speed, 2))
        await pilot.press("t")
        await pilot.pause(0.4)
        print("palette:", app.theme_index, app.query_one("SystemPanel").styles.background)
        await pilot.press("r")
        await pilot.pause(1.2)


asyncio.run(main())
