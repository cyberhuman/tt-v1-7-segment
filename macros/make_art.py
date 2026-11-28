#!/usr/bin/env python3
"""Turn a black-and-white picture into the art macro of the tile.

Usage: make_art.py [<picture>]

The picture is 38 pixels wide and 402 pixels tall, and a pixel lighter than mid-grey is
metal. Without an argument the script reads segment_art.png next to it. It writes
segment_art.gds and segment_art.lef next to itself.

The macro has the same picture on each of the four metal layers of the tile, Metal1 to
Metal4, one above the other. There are no vias between the layers, so the shapes connect to
nothing. The LEF file blocks all four layers over the whole macro, which keeps every wire
of the tile out of the picture.

The macro is 26 cell sites wide and 39 cell rows tall (14.56 by 152.88 um). One site wider,
and the power grid loses its first strap, which then stands 0.4 um from the macro.

One pixel is 0.38 um square: the smallest square that meets the minimum area of a metal
shape (0.1444 um2 on all four layers), and wider than the minimum width and spacing (0.23 um
on Metal1, 0.28 um on Metal2 to Metal4). The one pattern the rules do not allow is two metal
pixels that touch only at a corner; the script turns one of the two pixels beside such a
corner into metal and reports how many it added.
"""
import datetime
import os
import sys

import gdstk
from PIL import Image

NAME = "segment_art"
PIXEL = 0.38                     # um
WIDTH, HEIGHT = 14.56, 152.88    # um
COLUMNS, ROWS = 38, 402
LAYERS = {"Metal1": (34, 0), "Metal2": (36, 0), "Metal3": (42, 0), "Metal4": (46, 0)}
PR_BOUNDARY = (0, 0)

here = os.path.dirname(os.path.abspath(__file__))
picture = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, NAME + ".png")

img = Image.open(picture).convert("L")
if img.size != (COLUMNS, ROWS):
    sys.exit("picture is %dx%d, expected %dx%d" % (img.size + (COLUMNS, ROWS)))
on = [[img.getpixel((x, y)) >= 128 for x in range(COLUMNS)] for y in range(ROWS)]

added = 0
changed = True
while changed:
    changed = False
    for y in range(ROWS - 1):
        for x in range(COLUMNS - 1):
            a, b, c, d = on[y][x], on[y][x + 1], on[y + 1][x], on[y + 1][x + 1]
            if a and d and not b and not c:
                on[y][x + 1] = True
            elif b and c and not a and not d:
                on[y][x] = True
            else:
                continue
            added += 1
            changed = True

# The pixel grid sits in the middle of the macro; one rectangle per horizontal run of pixels
# on each layer.
x0 = round((WIDTH - COLUMNS * PIXEL) / 2, 3)
y0 = round((HEIGHT - ROWS * PIXEL) / 2, 3)
lib = gdstk.Library()
cell = lib.new_cell(NAME)
cell.add(gdstk.rectangle((0, 0), (WIDTH, HEIGHT), layer=PR_BOUNDARY[0], datatype=PR_BOUNDARY[1]))
runs = 0
for y in range(ROWS):
    bottom = y0 + (ROWS - 1 - y) * PIXEL
    x = 0
    while x < COLUMNS:
        if not on[y][x]:
            x += 1
            continue
        start = x
        while x < COLUMNS and on[y][x]:
            x += 1
        for layer, datatype in LAYERS.values():
            cell.add(gdstk.rectangle(
                (round(x0 + start * PIXEL, 3), round(bottom, 3)),
                (round(x0 + x * PIXEL, 3), round(bottom + PIXEL, 3)),
                layer=layer, datatype=datatype))
        runs += 1
# A fixed date in the file, so that the same picture always gives the same file.
lib.write_gds(os.path.join(here, NAME + ".gds"), timestamp=datetime.datetime(2026, 1, 1))

blocked = []
for layer in LAYERS:
    blocked += ["      LAYER %s ;" % layer, "        RECT 0.000 0.000 %.3f %.3f ;" % (WIDTH, HEIGHT)]
with open(os.path.join(here, NAME + ".lef"), "w") as f:
    f.write("\n".join([
        "VERSION 5.7 ;",
        "  NOWIREEXTENSIONATPIN ON ;",
        '  DIVIDERCHAR "/" ;',
        '  BUSBITCHARS "[]" ;',
        "MACRO %s" % NAME,
        "  CLASS BLOCK ;",
        "  FOREIGN %s ;" % NAME,
        "  ORIGIN 0.000 0.000 ;",
        "  SIZE %.3f BY %.3f ;" % (WIDTH, HEIGHT),
        "  OBS",
        *blocked,
        "  END",
        "END %s" % NAME,
        "END LIBRARY",
    ]) + "\n")

metal = sum(v for row in on for v in row)
print("%d of %d pixels are metal (%.0f%%), %d rectangles on each of %d layers, %d pixels added at corners"
      % (metal, COLUMNS * ROWS, 100 * metal / (COLUMNS * ROWS), runs, len(LAYERS), added))
