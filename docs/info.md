<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

A four-digit hexadecimal counter: a 16-bit count from 0000 to FFFF that wraps
to 0000. Each digit is a 4-bit counter with its own 7-segment pattern, and the
digits are chained: a digit steps when the digit before it goes from the last
digit of its base to 0. Each digit has its own base, set over SPI: the default
is 16 (hex) for all four. Bases 10, 6, 10, 6 (digit 0 first) make a clock that
counts 00:00 to 59:59 and wraps to 00:00. The display shows one digit at a time.

- `ui[0]` is **EN**, the count enable (carry-in of the lowest digit). With
  EN = 1 the counter adds 1 on each clock cycle. With EN = 0 it holds its
  value.
- `ui[1]` and `ui[2]` are **SEL0** and **SEL1**: they pick the digit shown,
  0 = lowest, 3 = highest. A change shows at once, without a clock edge.
- `uo[0]` to `uo[6]` drive the segments A to G (active high) of the digit shown.
- `uo[7]` is **CO**, the carry-out of the digit shown. It is high while EN = 1
  and that digit and all the digits below it are F. With the highest digit
  selected it is the carry-out of the whole counter.
- `uio[0]`, `uio[1]` and `uio[3]` are **CS** (active low), **MOSI** and
  **SCK** of an SPI port (mode 0, MSB first). A frame is 16 bits: the bases
  of digit 3, 2, 1 and 0, 4 bits each, in this order (0 means 16). On its 16th
  clock edge all four bases are taken. A frame cut short by CS going high changes nothing, and
  SCK edges while CS is high are ignored. There is no MISO.
- `rst_n` (active low) clears the counter, so all four digits are 0, and sets
  all four bases to 16.
- The SPI side has its own clock, SCK, with no synchroniser to `clk`, so it
  works with a slow clock or a push button. Write the bases between clock
  edges, not at the moment of one.
- The counts and the segment outputs are held in flip-flops, so all segments
  change together on the rising edge of `clk`.

| Pin | Name | Direction | Meaning |
|-----|------|-----------|---------|
| ui[0] | EN | in | count enable (carry-in) |
| ui[1] | SEL0 | in | digit select, low bit |
| ui[2] | SEL1 | in | digit select, high bit |
| uio[0] | CS | in | SPI chip select, active low |
| uio[1] | MOSI | in | SPI data in |
| uio[3] | SCK | in | SPI clock |
| uo[0] | A | out | segment A |
| uo[1] | B | out | segment B |
| uo[2] | C | out | segment C |
| uo[3] | D | out | segment D |
| uo[4] | E | out | segment E |
| uo[5] | F | out | segment F |
| uo[6] | G | out | segment G |
| uo[7] | CO | out | carry-out of the digit shown (decimal point) |

Clock and reset are the dedicated `clk` and `rst_n` pins. The other `ui` pins
and `uio` pins are unused; `uio[2]` is kept for MISO and is not driven.

## How to test

1. Put a 7-segment display on `uo[0]` to `uo[7]` (segments A to G, then the
   decimal point).
2. Set EN (`ui[0]`) to 1 and SEL (`ui[2:1]`) to 0, the lowest digit.
3. Pull `rst_n` low for a moment, then release it. The display shows 0 and all
   bases are 16. For a clock (10, 6, 10, 6), send one 16-bit SPI frame with the
   value 0x6A6A on CS, MOSI and SCK, between clock edges.
4. Apply a slow clock to `clk` (about 1 Hz) or press a push button. The display
   counts 0, 1, ... 9, A, b, C, d, E, F and wraps to 0 (with base 10 it stops at 9).
5. The decimal point (CO) lights while the display shows the last digit of its
   base (F by default).
6. Change SEL: the display shows the next digit, which steps once each time the
   lowest digit wraps (from F to 0, or from 9 to 0 with base 10).
7. Set EN to 0: all digits stop.

## External hardware

A 7-segment display on `uo[0]` to `uo[7]` (active high), switches for EN
(`ui[0]`) and SEL (`ui[1]`, `ui[2]`), an SPI controller (for example the
RP2040 on the demo board) on `uio[0]`, `uio[1]` and `uio[3]`, and a slow clock
source or a push button on `clk`.
