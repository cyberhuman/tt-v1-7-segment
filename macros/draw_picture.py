#!/usr/bin/env python3
"""Draw the picture for make_art.py: the text CYBER_V1|SG'26, where the bar is a double line.
The text runs up the picture, turned a quarter turn counter-clockwise, so it stands above
the design when the left edge of the tile is at the top.

Usage: draw_picture.py [<output picture>]

Writes segment_art.png next to this script unless another path is given.

The script draws the text as a line from left to right, 402 pixels long and 38 tall, and
turns the result. A character is drawn on a grid 25 pixels wide and 31 tall, with strokes
3 pixels thick, and takes the width of its own pixels. The gap between two characters is
8 pixels, or the number in KERNING for that pair. A character is a list of strokes:
  ("bar", left, top, right, bottom)        a filled rectangle, both corners included
  ("slope", x_top, x_bottom, top, bottom)  a slanted stroke, 4 pixels wide in every row,
                                           whose left edge runs from x_top to x_bottom
  ("ring", left, top, right, bottom, corners[, clip])
                                           the outline of a rectangle, 3 pixels thick, with
                                           the corners named in `corners` round (tl, tr, bl,
                                           br). Only the part inside the character's grid is
                                           drawn, so a rectangle that reaches 3 pixels past
                                           the grid has no side there. `clip` (left, top,
                                           right, bottom) limits the part drawn further.
"""
import os
import sys

from PIL import Image

LENGTH, HEIGHT = 402, 38         # pixels, before the turn: make_art.py expects 38 by 402
TEXT = "CYBER_V1|SG'26"
CHAR_WIDTH, CHAR_HEIGHT = 25, 31
GAP = 8
KERNING = {
    "_V": 2,                     # the arms of V lean away from the underscore
    "1|": 6, "|S": 6,
    "'2": 6,
}

TOP = ("bar", 0, 0, 24, 2)
BOTTOM = ("bar", 0, 28, 24, 30)
LEFT = ("bar", 0, 0, 2, 30)
STROKES = {
    "C": [("ring", 0, 0, 27, 30, "tl bl")],
    "Y": [("slope", 0, 10, 0, 15), ("slope", 21, 11, 0, 15), ("bar", 11, 15, 13, 30)],
    "B": [LEFT, ("ring", -3, 0, 22, 16, "tr br"), ("ring", -3, 14, 24, 30, "tr br")],
    "E": [LEFT, TOP, ("bar", 0, 14, 18, 16), BOTTOM],
    "R": [LEFT, ("ring", -3, 0, 24, 16, "tr br"), ("slope", 9, 21, 17, 30)],
    "_": [BOTTOM],
    "V": [("slope", 0, 10, 0, 30), ("slope", 21, 11, 0, 30)],
    "1": [("bar", 11, 0, 13, 30), ("bar", 5, 28, 19, 30), ("bar", 5, 0, 13, 2)],
    "S": [("ring", 0, 0, 27, 16, "tl bl", (0, 0, 24, 13)), ("ring", 0, 0, 27, 16, "tl bl", (0, 14, 12, 16)),
          ("ring", -3, 14, 24, 30, "tr br", (12, 14, 24, 16)), ("ring", -3, 14, 24, 30, "tr br", (0, 17, 24, 30))],
    "G": [("ring", 0, 0, 27, 30, "tl", (0, 0, 24, 13)), ("ring", 0, 0, 24, 30, "bl br", (0, 14, 24, 30)),
          ("bar", 12, 14, 24, 16)],
    "'": [("bar", 0, 0, 2, 8)],
    "2": [("ring", -3, 0, 24, 16, "tr br", (0, 0, 24, 13)), ("ring", -3, 0, 24, 16, "tr br", (12, 14, 24, 16)),
          ("ring", 0, 14, 27, 30, "tl", (0, 14, 12, 16)), ("ring", 0, 14, 27, 30, "tl", (0, 17, 24, 30))],
    "6": [("ring", 0, 0, 27, 30, "tl", (0, 0, 24, 13)), ("ring", 0, 14, 24, 30, "tr bl br")],
    "|": [("bar", 0, -2, 0, 33), ("bar", 2, -2, 2, 33)],     # two lines, one pixel apart
}

STROKE = 3                       # thickness of the outline of a ring
RADIUS = 7                       # radius of its round corners


def in_round_box(x, y, left, top, right, bottom, radius, corners):
    """Whether pixel (x, y) is in the rectangle with the named corners round."""
    if not (left <= x <= right and top <= y <= bottom):
        return False
    for name in corners.split():
        dx = left + radius - x if name[1] == "l" else x - (right - radius)
        dy = top + radius - y if name[0] == "t" else y - (bottom - radius)
        if dx > 0 and dy > 0 and dx * dx + dy * dy > (radius + 0.4) ** 2:
            return False
    return True


def pixels(kind, *args):
    """The pixels of one stroke on the grid of its character."""
    if kind == "bar":
        left, top, right, bottom = args
        return {(x, y) for y in range(top, bottom + 1) for x in range(left, right + 1)}
    if kind == "slope":
        x_top, x_bottom, top, bottom = args
        return {(round(x_top + (x_bottom - x_top) * (y - top) / (bottom - top)) + dx, y)
                for y in range(min(top, bottom), max(top, bottom) + 1) for dx in range(4)}
    left, top, right, bottom, corners = args[:5]
    clip = args[5] if len(args) > 5 else (0, 0, CHAR_WIDTH - 1, CHAR_HEIGHT - 1)
    return {(x, y) for y in range(clip[1], clip[3] + 1) for x in range(clip[0], clip[2] + 1)
            if in_round_box(x, y, left, top, right, bottom, RADIUS, corners)
            and not in_round_box(x, y, left + STROKE, top + STROKE, right - STROKE, bottom - STROKE,
                                 RADIUS - STROKE, corners)}


# Every character, moved so that its leftmost pixel is in column 0, and its width.
glyphs = []
for char in TEXT:
    dots = set().union(*(pixels(*stroke) for stroke in STROKES[char]))
    left = min(x for x, y in dots)
    glyphs.append(({(x - left, y) for x, y in dots}, max(x for x, y in dots) - left + 1))
gaps = [KERNING.get(a + b, GAP) for a, b in zip(TEXT, TEXT[1:])]
length = sum(width for dots, width in glyphs) + sum(gaps)
if length > LENGTH:
    sys.exit("the text is %d pixels long, the picture %d" % (length, LENGTH))

on = [[False] * LENGTH for _ in range(HEIGHT)]
left = (LENGTH - length) // 2
top = (HEIGHT - CHAR_HEIGHT) // 2
for (dots, width), gap in zip(glyphs, gaps + [0]):
    for x, y in dots:
        on[top + y][left + x] = True
    left += width + gap

# The quarter turn counter-clockwise: the top of the text goes to the left edge of the
# picture, and the start of the text to the bottom.
turned = [[on[x][LENGTH - 1 - y] for x in range(HEIGHT)] for y in range(LENGTH)]

out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "segment_art.png")
img = Image.new("L", (HEIGHT, LENGTH))
img.putdata([255 if v else 0 for row in turned for v in row])
img.save(out)
