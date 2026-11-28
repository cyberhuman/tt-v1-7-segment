![](../../workflows/gds/badge.svg) ![](../../workflows/docs/badge.svg) ![](../../workflows/test/badge.svg) ![](../../workflows/fpga/badge.svg)

# v1 - 7-segment indicator counter

A four-digit counter for a 7-segment display, made for Tiny Tapeout on the
GF180MCU process. It is written in Verilog and takes one tile.

- Each digit counts in its own base, up to 16, so the same chip counts in
  hexadecimal, in decimal, or as a clock (minutes and seconds, 24 hours,
  12 hours).
- It counts up or down, on `clk` or on the INC and DEC pins.
- It shows one digit at a time: the digit picked by two pins, or each digit in
  turn for a multiplexed four-digit display. It also drives the two-digit
  7-segment Pmod of Tiny Tapeout.
- The bases, the display options and the count itself are set and read over
  SPI.

[The documentation](docs/info.md) has the pins, the registers, the timing
rules and how to test the chip.

## Files

| Path | What it is |
|------|------------|
| [src/project.v](src/project.v) | the design; the top module is `tt_um_cyberhuman_7segment` |
| [src/config.json](src/config.json), [src/project.sdc](src/project.sdc) | settings and timing constraints for hardening |
| [src/segment_art.v](src/segment_art.v), [macros/](macros) | the picture in metal at the left edge of the tile |
| [test/test.py](test/test.py) | the tests (cocotb) |
| [docs/info.md](docs/info.md) | the documentation, which becomes the datasheet |
| [info.yaml](info.yaml) | the project description and the pinout for Tiny Tapeout |

## Running the tests

The tests need Icarus Verilog and the Python packages in
[test/requirements.txt](test/requirements.txt).

```sh
cd test
make -B                          # the design as written
make -B COMPILE_ARGS=-DSYNTH     # the variant built for the FPGA
make -B GATES=yes                # the hardened netlist, without delays
make -B GATES=yes SDF=<file>     # the hardened netlist, with the delays of one corner
```

The last two need `PDK_ROOT` set and the netlist of a hardened design
(`runs/wokwi/final/pnl/*.pnl.v`) copied to `test/gate_level_netlist.v`.

## The picture

The left edge of the tile has a picture in metal: the text `CYBER_V1|SG'26`,
where the bar is a double line. The text runs up the edge, turned a quarter
turn counter-clockwise, so it stands above the design when the left edge of
the tile is at the top. The picture is 38 pixels wide and 402 tall, and a
pixel is 0.38 µm square. The same shapes are on all four metal layers of the tile,
Metal1 to Metal4, one above the other, with no vias between them.

The picture is a macro without pins or logic. `MACROS` in
[src/config.json](src/config.json) places it. It takes the place of the first
26 cell sites of every row, and no wire of the tile crosses it.

```sh
python macros/draw_picture.py    # draws macros/segment_art.png
python macros/make_art.py        # makes macros/segment_art.gds and .lef from it
```

The two scripts need the Python packages `gdstk` and `pillow`, which the Tiny
Tapeout tools install. `make_art.py` takes any black-and-white picture of
38 by 402 pixels, where white is metal. Two metal pixels must not touch only at
a corner; the script adds a pixel beside such a corner.

## What is Tiny Tapeout?

Tiny Tapeout is an educational project that aims to make it easier and cheaper than ever to get your digital and analog designs manufactured on a real chip.

To learn more and get started, visit https://tinytapeout.com.

## Resources

- [FAQ](https://tinytapeout.com/faq/)
- [Digital design lessons](https://tinytapeout.com/digital_design/)
- [Learn how semiconductors work](https://tinytapeout.com/siliwiz/)
- [Join the community](https://tinytapeout.com/discord)
- [Build your design locally](https://www.tinytapeout.com/guides/local-hardening/)
