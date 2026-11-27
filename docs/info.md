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

- `ui[3]` is **EN**, the count enable (carry-in of the lowest digit). With
  EN = 1 the counter steps on each counter clock edge. With EN = 0 it holds
  its value. EN works in every count mode.
- `ui[4]` is **INC** and `ui[5]` is **DEC**, the counting inputs in the count
  modes 1 to 3. INC counts up and DEC counts down, each when it is pressed:
  the step comes on the rising edge of the pin, nothing happens on release.
  `clk` does not count then. Use one at a time: pressing both together is not
  defined. INC and DEC pulses, and the gaps between them, should be at
  least 100 ns. In mode 0 INC and DEC are ignored.
- `uio[4]` and `uio[5]` are **SEL0** and **SEL1** in the count modes 0 and 1:
  inputs that pick the digit shown, 0 = lowest, 3 = highest. A change shows at
  once, without a clock edge. In the modes 2 and 3 the chip picks the digit
  itself and these pins, with `uio[6]` and `uio[7]`, are outputs: **DIG0** to
  **DIG3** (below).
- `uo[0]` to `uo[6]` drive the segments A to G (active high) of the digit shown.
- `uo[7]` is **DP**, the decimal point of the digit shown. Its DOT value
  (below) makes it off, on, the carry-out CO of that digit, or the inverse of
  CO. CO is high while EN = 1 and that digit and all the digits below it are
  F; with the highest digit selected it is the carry-out of the whole counter.
  After reset it is CO.
- `ui[0]`, `ui[1]` and `ui[2]` are **CS** (active low), **MOSI** and
  **SCK** of an SPI port (mode 0, MSB first) that writes registers. A write is
  16 bits: an address byte, then a data byte. The register takes the data on
  the 16th clock edge, and more writes can follow while CS stays low. A write
  cut short by CS going high changes nothing, and so do SCK edges while CS is
  high. Bit 7 of the address is reserved for reads, so a write with it set
  changes nothing, and neither does an address without a register. There is
  no MISO yet.
- `rst_n` (active low) clears the counter, so all four digits are 0, sets all
  four bases to 16, all display modes to 0 (every digit is shown as is) and
  all DOT values to 2 (the decimal point is CO) the direction to up and the count mode to 0. A display mode changes the segments
  only, and DOT changes bit 7 only; neither affects the counting.
- The SPI side has its own clock, SCK, with no synchroniser to `clk`, so it
  works with a slow clock or a push button. Write the bases between clock
  edges, not at the moment of one.
- The counts are held in flip-flops and the segments are decoded from them, so
  all segments change together after the rising edge of the counter clock.

| Address | Register | Reset | Data bits |
|---------|----------|-------|-----------|
| 0x00 | BASE10 | 0x00 | 7:4 base of digit 1, 3:0 base of digit 0 (0 means 16) |
| 0x01 | BASE32 | 0x00 | 7:4 base of digit 3, 3:0 base of digit 2 (0 means 16) |
| 0x02 | MODE | 0x00 | 7:6 mode of digit 3, 5:4 digit 2, 3:2 digit 1, 1:0 digit 0 |
| 0x03 | DOT | 0xAA | 7:6 dot of digit 3, 5:4 digit 2, 3:2 digit 1, 1:0 digit 0 |
| 0x04 | CTRL | 0x00 | 7:3 unused; 2 UP/DOWN (0 counts up, 1 counts down); 1:0 count mode |
| 0x05 | COUNT10 | 0x00 | 7:4 count of digit 1, 3:0 count of digit 0 |
| 0x06 | COUNT32 | 0x00 | 7:4 count of digit 3, 3:0 count of digit 2 |

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

DIG0 to DIG3 are one line per digit, active high, one high at a time.

Counting down: each digit goes down by 1, and a digit at 0 wraps to the last
digit of its base (F for base 16). A digit steps when the digit before it
wraps, so 0000 goes to FFFF, and with bases 10, 6, 10, 6 the clock goes from
00:00 to 59:59. CO is then the borrow: high while EN = 1 and that digit and all
the digits below it are 0. In the modes 1 to 3 CO is the carry or the borrow
according to which of INC and DEC was pressed last, and the carry until one
is pressed.

Counting on the pins (modes 1 to 3): the step comes when INC or DEC is pressed.
Both next counts, up and down, are worked out all the time, and the DEC pin
itself picks one in front of the flip-flops (INC leaves DEC low, so up waits).
The counter clock is a delayed copy of INC or DEC, so the pick is made before
the edge arrives.

Changing the count mode: the switch of the counter clock between `clk` and the
pins is not glitch-free. A write to the mode may make one edge on the counter
clock, which can count or load once, and a mode write while `clk` is high does
give the counter one edge. So change the mode while `clk` is low or EN is low,
and write the count after the mode.

Setting the count: a write to COUNT10 or COUNT32 is taken on the next rising
edge of the counter clock (`clk` in mode 0, the press of INC or DEC in the
other modes), which loads those two digits instead of counting, whatever EN
and the direction are. Writing the same value again loads again, and writing
both registers before one edge loads all four digits on that edge. A digit that
loads has no carry-out on that edge, and a value at or above the base is taken
as is. Reset clears the written values, so it never causes a load.

Scan (modes 2 and 3): a 2-bit scan counter steps 0, 1, 2, 3, 0 on every
rising edge of `clk`, whatever EN is. The digit it names is the one on `uo`,
with its own dot value on DP. The scan counter holds in modes 0 and 1 and
carries on from where it was; reset clears it. It takes the mode from the SPI
side without a synchroniser, like the other settings. `clk` is the scan rate:
run it at about 1 kHz or more so the four digits look steady, or at 1 Hz to
watch them one by one.

| Pin | Name | Direction | Meaning |
|-----|------|-----------|---------|
| ui[0] | CS | in | SPI chip select, active low |
| ui[1] | MOSI | in | SPI data in |
| ui[2] | SCK | in | SPI clock |
| ui[3] | EN | in | count enable (carry-in) |
| ui[4] | INC | in | counts up on press, count modes 1 to 3 |
| ui[5] | DEC | in | counts down on press, count modes 1 to 3 |
| uio[4] | SEL0 / DIG0 | in / out | digit select low bit (modes 0, 1); scan number low bit (mode 2) or digit 0 line (mode 3) |
| uio[5] | SEL1 / DIG1 | in / out | digit select high bit (modes 0, 1); scan number high bit (mode 2) or digit 1 line (mode 3) |
| uio[6] | DIG2 | out | digit 2 line, mode 3 only |
| uio[7] | DIG3 | out | digit 3 line, mode 3 only |
| uo[0] | A | out | segment A |
| uo[1] | B | out | segment B |
| uo[2] | C | out | segment C |
| uo[3] | D | out | segment D |
| uo[4] | E | out | segment E |
| uo[5] | F | out | segment F |
| uo[6] | G | out | segment G |
| uo[7] | DP | out | decimal point of the digit shown (CO by default) |

Clock and reset are the dedicated `clk` and `rst_n` pins. The other `ui` pins
and `uio[0]`, `uio[1]` and `uio[3]` are unused; `uio[2]` is kept for MISO and is not driven.

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
source or a push button on `clk`.

For a four-digit multiplexed display, set the mode to 2 or 3 and put the four
digits' segment pins in parallel on `uo[0]` to `uo[7]`. Mode 2: a 2-to-4
decoder on `uio[5:4]` picks the digit common. Mode 3: wire `uio[4]` to `uio[7]`
straight to the digit commons, 0 to 3 (through transistors if the
segments draw more than the pins give).
