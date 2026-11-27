<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

A four-digit counter for a 7-segment display. Each digit counts in its own
base, and the digits are chained: a digit steps when the digit below it wraps.
The display shows one digit at a time. The bases, the display options and the
count are set over SPI.

### Pins

| Pin | Name | Direction | Meaning |
|-----|------|-----------|---------|
| `ui[0]` | CS | in | SPI chip select, active low |
| `ui[1]` | MOSI | in | SPI data in |
| `ui[2]` | SCK | in | SPI clock |
| `ui[3]` | EN | in | count enable |
| `ui[4]` | INC | in | counts up when pressed (count modes 1 to 3) |
| `ui[5]` | DEC | in | counts down when pressed (count modes 1 to 3) |
| `uio[0]` | BORROW | out | borrow-out of the whole counter |
| `uio[1]` | CARRY | out | carry-out of the whole counter |
| `uio[4]` | SEL0 / DIG0 | in / out | digit select, low bit (modes 0, 1); scan number, low bit (mode 2); digit 0 line (mode 3) |
| `uio[5]` | SEL1 / DIG1 | in / out | digit select, high bit (modes 0, 1); scan number, high bit (mode 2); digit 1 line (mode 3) |
| `uio[6]` | DIG2 | out | digit 2 line (mode 3) |
| `uio[7]` | DIG3 | out | digit 3 line (mode 3) |
| `uo[0]` to `uo[6]` | A to G | out | segments of the digit shown, active high |
| `uo[7]` | DP | out | decimal point of the digit shown |
| `clk` | | in | counts (mode 0) or steps the scan (modes 2, 3) |
| `rst_n` | | in | reset, active low |

`ui[6]`, `ui[7]` and `uio[3]` are unused; `uio[2]` is kept for MISO and is not
driven.

### Counting

Each digit is a 4-bit counter with a base of up to 16. Counting up, it goes
from 0 to the last digit of its base (F for base 16, 9 for base 10) and wraps
to 0; counting down, it wraps from 0 to the last digit. A digit steps when the
digit below it wraps. With base 16 for all four digits the count runs from
0000 to FFFF; with bases 10, 6, 10, 6 (digit 0 first) it runs from 00:00 to
59:59.

EN enables the count: with EN = 0 the counter holds its value. The count mode
sets what makes a step. In mode 0 it is the rising edge of `clk`, and the
UP/DOWN bit gives the direction. In the modes 1 to 3 it is a press of INC (up)
or DEC (down): the step comes on the rising edge of the pin, and nothing
happens on release.

Each digit has a carry-out, CO: high while EN = 1 and that digit and all the
digits below it are at the last digit of their base. Counting down, CO is the
borrow instead: high while EN = 1 and that digit and all the digits below it
are 0. In the modes 1 to 3 CO is the carry or the borrow according to which of
INC and DEC was pressed last, and the carry until one is pressed. CARRY and
BORROW are the carry-out and the borrow-out of all four digits. Both follow
the count whatever the direction, the digit shown and the display mode.

### Display

`uo[0]` to `uo[6]` carry the segments of one digit and `uo[7]` its decimal
point. In the count modes 0 and 1 SEL picks the digit, 0 for the lowest and 3
for the highest. In the modes 2 and 3 the chip scans the digits itself: a
2-bit scan counter steps 0, 1, 2, 3, 0 on every rising edge of `clk`, whatever
EN is, and the digit it names is the one shown. Mode 2 puts the scan number on
`uio[5:4]`. Mode 3 raises one of DIG0 to DIG3: one line per digit, active
high, one high at a time.

Each digit has a display mode and a dot value, in the tables below. The
display mode changes the segments only and the dot value the decimal point
only; neither affects the counting.

### Registers

CS, MOSI and SCK are an SPI port (mode 0, MSB first) that writes registers. A
write is 16 bits: an address byte, then a data byte. The register takes the
data on the 16th clock edge, and more writes can follow while CS stays low. A
write cut short by CS going high changes nothing, and so do SCK edges while CS
is high. Bit 7 of the address is reserved for reads, so a write with it set
changes nothing, and neither does an address without a register. There is no
MISO yet, so registers cannot be read back.

| Address | Register | Reset | Data bits |
|---------|----------|-------|-----------|
| 0x00 | BASE10 | 0x00 | 7:4 base of digit 1, 3:0 base of digit 0 (0 means 16) |
| 0x01 | BASE32 | 0x00 | 7:4 base of digit 3, 3:0 base of digit 2 (0 means 16) |
| 0x02 | MODE | 0x00 | 7:6 mode of digit 3, 5:4 digit 2, 3:2 digit 1, 1:0 digit 0 |
| 0x03 | DOT | 0xAA | 7:6 dot of digit 3, 5:4 digit 2, 3:2 digit 1, 1:0 digit 0 |
| 0x04 | CTRL | 0x00 | 7:3 unused; 2 UP/DOWN (0 counts up, 1 counts down); 1:0 count mode |
| 0x05 | COUNT10 | 0x00 | 7:4 count of digit 1, 3:0 count of digit 0 |
| 0x06 | COUNT32 | 0x00 | 7:4 count of digit 3, 3:0 count of digit 2 |

A write to COUNT10 or COUNT32 sets the count. It is taken on the next step
(the rising edge of `clk` in mode 0, a press of INC or DEC in the other
modes), which loads those two digits instead of counting, whatever EN and the
direction are. Writing the same value again loads again, and writing both
registers before one step loads all four digits on that step. A digit that
loads has no carry-out on that step, and a value at or above the base is taken
as is.

### Display mode (MODE, two bits per digit)

| Value | Reset | The digit shows |
|-------|-------|-----------------|
| 0 | Y | its count |
| 1 | | its count, and nothing while its own count is 0 |
| 2 | | nothing |
| 3 | | a minus (segment G only) |

### Dot value (DOT, two bits per digit)

| Value | Reset | DP (`uo[7]`) while that digit is shown |
|-------|-------|----------------------------------------|
| 0 | | off |
| 1 | | on |
| 2 | Y | CO |
| 3 | | the inverse of CO |

### Count mode (CTRL bits 1:0)

| Signal | Mode 0 (reset) | Mode 1 | Mode 2 | Mode 3 |
|--------|--------|--------|--------|--------|
| EN (`ui[3]`) | enables the count | enables the count | enables the count | enables the count |
| `clk` | counts | — | steps the scan | steps the scan |
| UP/DOWN (CTRL bit 2) | direction of the count | — | — | — |
| INC (`ui[4]`) | — | counts up | counts up | counts up |
| DEC (`ui[5]`) | — | counts down | counts down | counts down |
| `uio[4]` | in: SEL0 | in: SEL0 | out: scan number, low bit | out: DIG0 |
| `uio[5]` | in: SEL1 | in: SEL1 | out: scan number, high bit | out: DIG1 |
| `uio[6]` | — | — | — | out: DIG2 |
| `uio[7]` | — | — | — | out: DIG3 |
| Digit on `uo` | picked by SEL | picked by SEL | the scan number | the scan number |

### Reset

`rst_n` low clears the count and the scan counter, drops a written count that
has not been loaded yet, and sets every register to the reset value in the
table.

### Details

- INC and DEC: press one at a time; both together is not defined. Pulses, and
  the gaps between them, must be at least 100 ns.
- The SPI side has its own clock, SCK, with no synchroniser to `clk`, INC or
  DEC. Write registers between steps of the counter, not at the moment of one.
  The scan counter takes the count mode the same way.
- A change on SEL shows at once, without a clock edge.
- The counts are held in flip-flops and the segments are decoded from them, so
  all segments change together after a step.
- In the modes 1 to 3 both next counts, up and down, are worked out all the
  time, and the DEC pin itself picks one in front of the flip-flops (INC
  leaves DEC low, so up waits). The counter clock is a delayed copy of INC or
  DEC, so the pick is made before the edge arrives.
- The switch of the counter clock between `clk` and the pins is not
  glitch-free. A write to the count mode may make one edge on the counter
  clock, which can count or load once, and a write while `clk` is high does
  give the counter one edge. Change the count mode while `clk` is low or EN is
  low, and write the count after the mode.
- The scan counter holds in the modes 0 and 1 and carries on from where it
  was.

## How to test

1. Put a 7-segment display on `uo[0]` to `uo[7]` (segments A to G, then the
   decimal point).
2. Set EN (`ui[3]`) to 1 and SEL (`uio[5:4]`) to 0, the lowest digit.
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
(`ui[3]`), push buttons for INC and DEC (`ui[4]`, `ui[5]`) and SEL (`uio[4]`, `uio[5]`; outputs in the modes 2 and 3), an SPI controller (for example the
RP2040 on the demo board) on `ui[0]`, `ui[1]` and `ui[2]`, and a slow clock
source or a push button on `clk`. CARRY and BORROW (`uio[1]`, `uio[0]`) can
enable a further counter.

For a four-digit multiplexed display, set the mode to 2 or 3 and put the four
digits' segment pins in parallel on `uo[0]` to `uo[7]`. Mode 2: a 2-to-4
decoder on `uio[5:4]` picks the digit common. Mode 3: wire `uio[4]` to `uio[7]`
straight to the digit commons, 0 to 3 (through transistors if the
segments draw more than the pins give).
