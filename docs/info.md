<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

A one-digit hexadecimal counter: it counts from 0 to F on a 7-segment display
and wraps to 0.

- `ui[0]` is **EN**, the count enable (carry-in). With EN = 1 the counter adds 1
  on each clock cycle. With EN = 0 it holds its value.
- `uo[0]` to `uo[6]` drive the segments A to G (active high).
- `uo[7]` is **CO**, the carry-out. It is high while EN = 1 and the digit shown
  is F. On the display it is the decimal point.
- `rst_n` (active low) clears the counter, so the display shows 0.
- The count is held in two rows of four flip-flops. The first row takes the next
  value on the rising edge of `clk`. The second row copies it on the falling
  edge and drives the display and CO, so the digit changes on the falling edge.

| Pin | Name | Direction | Meaning |
|-----|------|-----------|---------|
| ui[0] | EN | in | count enable (carry-in) |
| uo[0] | A | out | segment A |
| uo[1] | B | out | segment B |
| uo[2] | C | out | segment C |
| uo[3] | D | out | segment D |
| uo[4] | E | out | segment E |
| uo[5] | F | out | segment F |
| uo[6] | G | out | segment G |
| uo[7] | CO | out | carry-out (decimal point) |

Clock and reset are the dedicated `clk` and `rst_n` pins. The other `ui` pins
and all `uio` pins are unused.

## How to test

1. Put a 7-segment display on `uo[0]` to `uo[7]` (segments A to G, then the
   decimal point).
2. Set EN (`ui[0]`) to 1.
3. Pull `rst_n` low for a moment, then release it. The display shows 0.
4. Apply a slow clock to `clk` (about 1 Hz). The display counts 0, 1, ... 9, A,
   b, C, d, E, F and wraps to 0.
5. The decimal point (CO) lights while the display shows F.
6. Set EN to 0: the count stops at the digit shown.

To chain two digits, connect this block's CO to the next block's EN and give
both the same `clk` and `rst_n`. The next digit then steps when this one goes
from F to 0.

## External hardware

A 7-segment display on `uo[0]` to `uo[7]` (active high), a switch for EN
(`ui[0]`), and a slow clock source or a push button on `clk`.
