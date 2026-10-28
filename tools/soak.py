"""Long-run leak check: drive the dashboard headless and watch RSS.

    uv run python tools/soak.py --seconds 180

The app is mounted at the full 240x55 layout, all timers (globe 10 fps,
process table, clock, info polls) keep running, and resident memory is
sampled every few seconds. A healthy dashboard plateaus; a rising last
third means something is accumulating (cache, widget, history).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import psutil  # noqa: E402

from cyberdeck.app import CyberDeck  # noqa: E402


async def soak(seconds: int, width: int, height: int, step: float) -> int:
    proc = psutil.Process()
    samples: list[tuple[float, float]] = []
    app = CyberDeck()
    async with app.run_test(size=(width, height)) as pilot:
        await pilot.pause(5.0)  # warm up caches, threads and font atlases
        t0 = time.monotonic()
        while (elapsed := time.monotonic() - t0) < seconds:
            await pilot.pause(step)
            samples.append((elapsed, proc.memory_info().rss / 1024 / 1024))
    if not samples:
        print("no samples")
        return 1

    first, last = samples[0][1], samples[-1][1]
    peak = max(m for _, m in samples)
    third = max(1, len(samples) // 3)
    early = sum(m for _, m in samples[:third]) / third
    late = sum(m for _, m in samples[-third:]) / third
    print(f"samples      {len(samples)} over {seconds}s at {width}x{height}")
    print(f"rss start    {first:6.1f} MB")
    print(f"rss peak     {peak:6.1f} MB")
    print(f"rss end      {last:6.1f} MB  ({last - first:+.1f} MB)")
    print(f"drift        {late - early:+.2f} MB between the first and last third")
    if late - early > 8:
        print("VERDICT: memory is still climbing, something is unbounded")
        return 1
    print("VERDICT: flat, safe to leave running")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=120)
    parser.add_argument("--width", type=int, default=240)
    parser.add_argument("--height", type=int, default=55)
    parser.add_argument("--step", type=float, default=5.0)
    args = parser.parse_args()
    return asyncio.run(soak(args.seconds, args.width, args.height, args.step))


if __name__ == "__main__":
    raise SystemExit(main())
