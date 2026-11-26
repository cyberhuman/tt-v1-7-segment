<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

A four-digit hexadecimal counter: a 16-bit count from 0000 to FFFF that wraps
to 0000. Each digit is a 4-bit counter with its own 7-segment pattern, and the
digits are chained: a digit steps when the digit before it goes from F to 0.
The display shows one digit at a time.

- `ui[0]` is **EN**, the count enable (carry-in of the lowest digit). With
  EN = 1 the counter adds 1 on each clock cycle. With EN = 0 it holds its
  value.
- `ui[1]` and `ui[2]` are **SEL0** and **SEL1**: they pick the digit shown,
  0 = lowest, 3 = highest. A change shows at once, without a clock edge.
- `uo[0]` to `uo[6]` drive the segments A to G (active high) of the digit shown.
- `uo[7]` is **CO**, the carry-out of the digit shown. It is high while EN = 1
  and that digit and all the digits below it are F. With the highest digit
  selected it is the carry-out of the whole counter.
- `rst_n` (active low) clears the counter, so all four digits are 0.
- The counts and the segment outputs are held in flip-flops, so all segments
  change together on the rising edge of `clk`.

| Pin | Name | Direction | Meaning |
|-----|------|-----------|---------|
| ui[0] | EN | in | count enable (carry-in) |
| ui[1] | SEL0 | in | digit select, low bit |
| ui[2] | SEL1 | in | digit select, high bit |
| uo[0] | A | out | segment A |
| uo[1] | B | out | segment B |
| uo[2] | C | out | segment C |
| uo[3] | D | out | segment D |
| uo[4] | E | out | segment E |
| uo[5] | F | out | segment F |
| uo[6] | G | out | segment G |
| uo[7] | CO | out | carry-out of the digit shown (decimal point) |

Clock and reset are the dedicated `clk` and `rst_n` pins. The other `ui` pins
and all `uio` pins are unused.

## How to test

1. Put a 7-segment display on `uo[0]` to `uo[7]` (segments A to G, then the
   decimal point).
2. Set EN (`ui[0]`) to 1 and SEL (`ui[2:1]`) to 0, the lowest digit.
3. Pull `rst_n` low for a moment, then release it. The display shows 0.
4. Apply a slow clock to `clk` (about 1 Hz) or press a push button. The display
   counts 0, 1, ... 9, A, b, C, d, E, F and wraps to 0.
5. The decimal point (CO) lights while the display shows F.
6. Change SEL: the display shows the next digit, which steps once each time the
   lowest digit goes from F to 0.
7. Set EN to 0: all digits stop.

## External hardware

A 7-segment display on `uo[0]` to `uo[7]` (active high), switches for EN
(`ui[0]`) and SEL (`ui[1]`, `ui[2]`), and a slow clock source or a push button
on `clk`.
