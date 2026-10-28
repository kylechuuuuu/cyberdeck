"""5-row pixel font for the big clock."""

from __future__ import annotations

GLYPHS: dict[str, list[str]] = {
    "0": [".###.", "#...#", "#...#", "#...#", ".###."],
    "1": ["..#..", ".##..", "..#..", "..#..", ".###."],
    "2": [".###.", "#...#", "...#.", "..#..", "#####"],
    "3": ["####.", "....#", ".###.", "....#", "####."],
    "4": ["#...#", "#...#", "#####", "....#", "....#"],
    "5": ["#####", "#....", "####.", "....#", "####."],
    "6": ["..##.", ".#...", "####.", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", "..#.."],
    "8": [".###.", "#...#", ".###.", "#...#", ".###."],
    "9": [".###.", "#...#", ".####", "...#.", ".##.."],
    ":": [".", "#", ".", "#", "."],
    " ": [".....", ".....", ".....", ".....", "....."],
}

HEIGHT = 5


def rows(text: str) -> list[str]:
    """Render text to 5 rows of '#' / '.' characters."""
    out = [""] * HEIGHT
    for i, ch in enumerate(text):
        glyph = GLYPHS.get(ch, GLYPHS[" "])
        for r in range(HEIGHT):
            out[r] += glyph[r] + (" " if i != len(text) - 1 else "")
    return out


def width(text: str) -> int:
    return sum(len(GLYPHS.get(c, GLYPHS[" "])[0]) + 1 for c in text) - 1
