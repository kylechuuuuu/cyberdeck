"""Headless interaction check: sizes, workers, keys, process table, screenshots."""

import asyncio
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from textual.geometry import Size  # noqa: E402

from cyberdeck import storage  # noqa: E402
from cyberdeck.app import CyberDeck  # noqa: E402
from cyberdeck.system import SystemPanel  # noqa: E402
from cyberdeck.weather import WeatherPanel  # noqa: E402

OUT = Path(__file__).parent


def snapshot_user_files() -> dict[str, tuple[Path | None, bytes | None]]:
    """Smoke tests press ctrl+s; keep the developer's real config/todo intact."""
    snap: dict[str, tuple[Path | None, bytes | None]] = {}
    for name in ("config.json", "todo.txt", "notes.txt"):
        path = storage.data_path(name)
        try:
            data = path.read_bytes() if path is not None and path.exists() else None
        except OSError:
            data = None
        snap[name] = (path, data)
    return snap


def restore_user_files(snap: dict[str, tuple[Path | None, bytes | None]]) -> None:
    for path, data in snap.values():
        if path is None:
            continue
        try:
            if data is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(data)
        except OSError:
            pass



async def size_guard() -> None:
    app = CyberDeck()
    async with app.run_test(size=(90, 24)) as pilot:
        await pilot.pause(0.5)
        print("small guard:", app.query_one("#body").display is False,
              app.query_one("TooSmalMsg").display is True)
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
        sysp = app.query_one(SystemPanel)
        print("weather loaded:", bool(wp.data), wp.data.location if wp.data else wp.error)
        print("globe:", globe.size, "panel:", sysp.size)
        print("gpu:", sysp.sampler.state.gpu)
        print("procs:", len(sysp.sampler.state.procs), "nics:", [(n.name, n.ipv4) for n in sysp.sampler.state.nics])
        print("acpi:", sysp.sampler.state.acpi_temp, "diskio:", [d.label for d in sysp.sampler.state.disk_ios])

        (OUT / "shot.svg").write_text(app.export_screenshot(), encoding="utf-8")

        # process table interactions
        print("sort/cursor:", sysp.sort_key, sysp.cursor)
        await pilot.press("down", "down")
        print("after down:", sysp.cursor)
        await pilot.press("s")
        print("sort ->", sysp.sort_key)
        await pilot.press("k")
        print("pending kill:", sysp.pending_kill is not None)
        await pilot.press("escape")
        print("cancelled:", sysp.pending_kill is None)

        # globe controls
        await pilot.press("space")
        await pilot.pause(0.4)
        y1 = globe.yaw
        await pilot.pause(0.6)
        print("paused:", globe.paused, "frozen:", abs(globe.yaw - y1) < 1e-9)
        await pilot.press("plus", "plus", "minus")
        print("speed:", round(globe.speed, 2))

        # themes: cycle + direct select + persistence
        await pilot.press("t")
        await pilot.pause(0.3)
        print("theme after t:", app.theme_index, app.query_one(SystemPanel).styles.background)
        await pilot.press("5")
        await pilot.pause(0.2)
        print("theme 5:", app.theme_index, "cfg:", app.config.get("theme"))
        await pilot.press("1")
        await pilot.pause(0.2)

    narrow = CyberDeck()
    async with narrow.run_test(size=(120, 34)) as pilot:
        await pilot.pause(7.0)
        print("narrow panel:", narrow.query_one(SystemPanel).size)
        (OUT / "shot_narrow.svg").write_text(narrow.export_screenshot(), encoding="utf-8")

    from cyberdeck.extras import InfoPanel

    wide = CyberDeck()
    async with wide.run_test(size=(240, 55)) as pilot:
        await pilot.pause(7.0)
        info = wide.query_one(InfoPanel)
        print("info:", info.display, info.size, "lat:", round(info.state.latency[-1], 1) if info.state.latency else None,
              "quotes:", len(info.state.quotes), "air:", info.state.air)
        (OUT / "shot_full.svg").write_text(wide.export_screenshot(), encoding="utf-8")
        await pilot.press("i")
        await pilot.pause(0.5)
        print("info after i:", info.display, "cfg:", wide.config.get("info", {}).get("enabled"))
        await pilot.press("i")
        await pilot.pause(0.3)
        print("info restored:", info.display)

    # editor: stocks + todo, then save
    from textual.widgets import Input, TextArea

    edit = CyberDeck()
    async with edit.run_test(size=(240, 55)) as pilot:
        await pilot.pause(5.0)
        await pilot.press("e")
        await pilot.pause(0.6)
        screen = edit.screen
        print("editor:", type(screen).__name__)
        screen.query_one("#stocks", Input).value = "sh000001, sz399001, sh600519, us.AAPL"
        screen.query_one("#location", Input).value = "30.2741, 120.1551, Hangzhou"
        screen.query_one("#todo", TextArea).text = (
            "- [x] 给地球加定位标注\n"
            "- [ ] 信息栏布局再优化\n"
            "- [ ] 写性能基准测试\n"
        )
        await pilot.press("ctrl+s")
        await pilot.pause(1.2)
        panel = edit.query_one(InfoPanel)
        print("saved stocks:", panel.stocks, "todo:", panel.state.todo)
        print("todo file:", panel._todo_file(), panel._todo_file().exists())
        print("location cfg:", edit.config.get("location"), "marker:", edit.query_one("Globe").marker)

    # marker screenshot: face the location, pause, capture
    shot = CyberDeck()
    async with shot.run_test(size=(240, 55)) as pilot:
        await pilot.pause(6.0)
        globe = shot.query_one("Globe")
        await pilot.press("space")
        await pilot.pause(0.4)
        if globe.marker:
            lat, lon, name = globe.marker
            globe.yaw = -math.radians(lon)
            globe.refresh()
            await pilot.pause(0.3)
            print("marker:", name, lat, lon, "visible:", globe.engine.marker_pos is not None)
        await pilot.press("space")  # resume so the caption shows the spin rate
        await pilot.pause(0.25)
        (OUT / "shot_marker.svg").write_text(shot.export_screenshot(), encoding="utf-8")

        import time

        from cyberdeck.globe import image_to_text

        w, h = globe.size.width, globe.size.height
        marker = (globe.marker[0], globe.marker[1]) if globe.marker else None
        t0 = time.perf_counter()
        for _ in range(20):
            img = globe.engine.render(w, h, globe.yaw, time.time(), marker=marker)
        eng_ms = (time.perf_counter() - t0) / 20 * 1000
        t0 = time.perf_counter()
        for _ in range(20):
            image_to_text(img, "EARTH", hud=["ORBITAL VIEW"], labels=[(10, 6, "◉ Tokyo", (255, 80, 90))])
        txt_ms = (time.perf_counter() - t0) / 20 * 1000
        t0 = time.perf_counter()
        for _ in range(20):
            globe.render()
        print(f"globe: engine {eng_ms:.2f}ms text {txt_ms:.2f}ms full {(time.perf_counter()-t0)/20*1000:.2f}ms")


snap = snapshot_user_files()
try:
    asyncio.run(main())
finally:
    restore_user_files(snap)
    print("restored config/todo/notes")

