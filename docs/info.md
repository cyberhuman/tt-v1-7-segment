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
counts 00:00 to 59:59 and wraps to 00:00. Each digit also has a display mode:
show it as is, show it unless it is 0 (so a 0 can be left blank), show
nothing, or show a minus. The decimal point of each digit can be off, on, the
carry-out of the digit or its inverse. The display shows one digit at a time.

- `ui[0]` is **EN**, the count enable (carry-in of the lowest digit). With
  EN = 1 the counter adds 1 on each clock cycle. With EN = 0 it holds its
  value.
- `ui[1]` and `ui[2]` are **SEL0** and **SEL1**: they pick the digit shown,
  0 = lowest, 3 = highest. A change shows at once, without a clock edge.
- `uo[0]` to `uo[6]` drive the segments A to G (active high) of the digit shown.
- `uo[7]` is **DP**, the decimal point of the digit shown. Its DOT value
  (below) makes it off, on, the carry-out CO of that digit, or the inverse of
  CO. CO is high while EN = 1 and that digit and all the digits below it are
  F; with the highest digit selected it is the carry-out of the whole counter.
  After reset it is CO.
- `uio[0]`, `uio[1]` and `uio[3]` are **CS** (active low), **MOSI** and
  **SCK** of an SPI port (mode 0, MSB first) that writes registers. A write is
  16 bits: an address byte, then a data byte. The register takes the data on
  the 16th clock edge, and more writes can follow while CS stays low. A write
  cut short by CS going high changes nothing, and so do SCK edges while CS is
  high. Bit 7 of the address is reserved for reads, so a write with it set
  changes nothing, and neither does an address without a register. There is
  no MISO yet.
- `rst_n` (active low) clears the counter, so all four digits are 0, sets all
  four bases to 16, all display modes to 0 (every digit is shown as is) and
  all DOT values to 2 (the decimal point is CO). A mode changes the segments
  only, and DOT changes bit 7 only; neither affects the counting.
- The SPI side has its own clock, SCK, with no synchroniser to `clk`, so it
  works with a slow clock or a push button. Write the bases between clock
  edges, not at the moment of one.
- The counts and the segment outputs are held in flip-flops, so all segments
  change together on the rising edge of `clk`.

| Address | Register | Data bits |
|---------|----------|-----------|
| 0x00 | BASE10 | 7:4 base of digit 1, 3:0 base of digit 0 (0 means 16) |
| 0x01 | BASE32 | 7:4 base of digit 3, 3:0 base of digit 2 (0 means 16) |
| 0x02 | MODE | 7:6 mode of digit 3, 5:4 digit 2, 3:2 digit 1, 1:0 digit 0 |
| 0x03 | DOT | 7:6 dot of digit 3, 5:4 digit 2, 3:2 digit 1, 1:0 digit 0 |

Display modes: 0 shows the digit, 1 shows it unless its own count is 0 (then
all segments are off), 2 shows nothing, 3 shows a minus (segment G only).

Dot values: 0 is off (bit 7 low), 1 is on (bit 7 high), 2 is CO, 3 is the
inverse of CO. The reset value of DOT is 0xAA.

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
| uo[7] | DP | out | decimal point of the digit shown (CO by default) |

Clock and reset are the dedicated `clk` and `rst_n` pins. The other `ui` pins
and `uio` pins are unused; `uio[2]` is kept for MISO and is not driven.

## How to test

1. Put a 7-segment display on `uo[0]` to `uo[7]` (segments A to G, then the
   decimal point).
2. Set EN (`ui[0]`) to 1 and SEL (`ui[2:1]`) to 0, the lowest digit.
3. Pull `rst_n` low for a moment, then release it. The display shows 0 and all
   bases are 16. For a clock (10, 6, 10, 6), write 0x00 = 0x6A and 0x01 = 0x6A
   over SPI (CS, MOSI and SCK), between clock edges. To leave a 0 blank on
   the three upper digits, write 0x02 = 0x54.
4. Apply a slow clock to `clk` (about 1 Hz) or press a push button. The display
   counts 0, 1, ... 9, A, b, C, d, E, F and wraps to 0 (with base 10 it stops at 9).
5. The decimal point (CO by default) lights while the display shows the last digit of its
   base (F by default).
6. Change SEL: the display shows the next digit, which steps once each time the
   lowest digit wraps (from F to 0, or from 9 to 0 with base 10).
7. Set EN to 0: all digits stop.

## External hardware

A 7-segment display on `uo[0]` to `uo[7]` (active high), switches for EN
(`ui[0]`) and SEL (`ui[1]`, `ui[2]`), an SPI controller (for example the
RP2040 on the demo board) on `uio[0]`, `uio[1]` and `uio[3]`, and a slow clock
source or a push button on `clk`.
