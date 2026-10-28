"""Offline test: render a globe frame straight to PNG."""

import pathlib
import sys
import time

import numpy as np
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from cyberdeck.globe import GlobeEngine  # noqa: E402

W, H = 54, 20
eng = GlobeEngine()
frames = []
for i, yaw in enumerate([-1.9, 0.0, 1.2, 2.6]):
    img = eng.render(W, H, yaw, time.time())
    frames.append(img)

grid = np.concatenate([np.concatenate(frames[:2], axis=1), np.concatenate(frames[2:], axis=1)], axis=0)
scale = 6
big = np.repeat(np.repeat(grid, scale, axis=0), scale, axis=1)
Image.fromarray(big).save(pathlib.Path(__file__).parent / "globe_preview.png")
print("grid", grid.shape, "->", big.shape)
