<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

A four-digit counter for a 7-segment display. Each digit counts in its own
base, and a digit steps when the digit below it wraps. The display shows one
digit at a time. The bases, the display options and the count are set and read
over SPI.

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
| `uio[2]` | MISO | out | SPI data out, driven while CS is low |
| `uio[4]` | SEL0 / DIG0 | in / out | digit select, low bit; an output in count modes 2 and 3 |
| `uio[5]` | SEL1 / DIG1 | in / out | digit select, high bit; an output in count modes 2 and 3 |
| `uio[6]` | DIG2 | out | digit 2 line (count mode 3) |
| `uio[7]` | DIG3 | out | digit 3 line (count mode 3) |
| `uo[0]` to `uo[6]` | A to G | out | segments of the digit shown, active high |
| `uo[7]` | DP | out | decimal point of the digit shown |
| `clk` | | in | counts (count mode 0) or steps the scan (count modes 2, 3) |
| `rst_n` | | in | reset, active low |

`ui[6]`, `ui[7]` and `uio[3]` are unused.

### Counting

Each digit is a 4-bit counter with a base of up to 16. Counting up, it goes
from 0 to the last digit of its base (9 for base 10, F for base 16) and wraps
to 0. Counting down, it wraps from 0 to the last digit.

EN enables the count: with EN = 0 the counter holds. In count mode 0 a step is
a rising edge of `clk`, up or down by the UP/DOWN bit. In count modes 1 to 3 a
step is a press of INC (up) or DEC (down): the rising edge of the pin counts
and the release does nothing.

Digit 2 can have a second base, which it uses while digit 3 is at the last
digit of its own base. That is what stops the hours of a clock at 23 or at 11.
It holds in both directions: counting down, 00:00 goes to 23:59.

| Output | High while EN = 1 and |
|--------|-----------------------|
| CARRY | all four digits are at the last digit of their base |
| BORROW | all four digits are 0 |
| CO of a digit, counting up | that digit and all the digits below it are at the last digit of their base |
| CO of a digit, counting down | that digit and all the digits below it are 0 |

CO is what the decimal point can show. Its direction is the UP/DOWN bit in
count mode 0, and in count modes 1 to 3 the pin pressed last (up until one is
pressed).

### Display

`uo[0]` to `uo[6]` carry the segments of one digit and `uo[7]` its decimal
point. In count modes 0 and 1 SEL picks the digit: 0 for the lowest, 3 for the
highest. In count modes 2 and 3 the chip scans the digits itself, one digit
further on every rising edge of `clk`, whatever EN is. Mode 2 puts the number
of the digit shown on `uio[5:4]`. Mode 3 raises one of DIG0 to DIG3, one line
per digit.

Each digit has a display mode, for the segments, and a dot value, for the
decimal point. Neither affects the counting.

### SPI

CS, MOSI, SCK and MISO are an SPI port, mode 0, most significant bit first.
Every transfer is 16 clocks: an address byte, then a data byte.

| Transfer | Address byte | Data byte |
|----------|--------------|-----------|
| Write | the address | on MOSI; the register takes it on the last clock |
| Read | the address with bit 7 set (0x80 + address) | sent by the chip on MISO |

Transfers can follow each other while CS stays low. One cut short by CS going
high changes nothing. An address without a register and reserved bits read 0,
and a write to them does nothing.

### Registers

| Address | Register | Reset | Data bits |
|---------|----------|-------|-----------|
| 0x00 | BASE10 | 0x00 | 7:4 base of digit 1, 3:0 base of digit 0 (0 means 16) |
| 0x01 | BASE32 | 0x00 | 7:4 base of digit 3, 3:0 base of digit 2 (0 means 16) |
| 0x02 | MODE | 0x00 | display mode: 7:6 digit 3, 5:4 digit 2, 3:2 digit 1, 1:0 digit 0 |
| 0x03 | DOT | 0xAA | dot value: 7:6 digit 3, 5:4 digit 2, 3:2 digit 1, 1:0 digit 0 |
| 0x04 | CTRL | 0x00 | 7:3 unused; 2 UP/DOWN (0 counts up, 1 counts down); 1:0 count mode |
| 0x05 | COUNT10 | 0x00 | 7:4 count of digit 1, 3:0 count of digit 0 |
| 0x06 | COUNT32 | 0x00 | 7:4 count of digit 3, 3:0 count of digit 2 |
| 0x08 | ALT10 | | reserved |
| 0x09 | ALT32 | 0x00 | 7:4 reserved; 3:0 second base of digit 2 (0 means none) |

COUNT10 and COUNT32 are the count itself. A write sets those two digits at
once, in every count mode and whatever EN is, and a read returns what they
hold now. A value at or above the base is taken as is.

### Example settings

| Count | BASE10 | BASE32 | ALT32 | Runs |
|-------|--------|--------|-------|------|
| Hexadecimal | 0x00 | 0x00 | 0x00 | 0000 to FFFF |
| Decimal | 0xAA | 0xAA | 0x00 | 0000 to 9999 |
| Minutes and seconds | 0x6A | 0x6A | 0x00 | 00:00 to 59:59 |
| 24-hour clock | 0x6A | 0x3A | 0x04 | 00:00 to 23:59 |
| 12-hour clock | 0x6A | 0x2A | 0x02 | 00:00 to 11:59 |

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

`rst_n` low clears the count and the scan, and sets every register to its
reset value.

### Timing rules

| Rule | Otherwise |
|------|-----------|
| Press INC and DEC one at a time, with pulses and the gaps between them of at least 100 ns | the step is not defined |
| Write and read registers between steps of the counter, not during one | the value written or read is not defined |
| Change the count mode while `clk` is low or EN is low, and set the count after it | the counter may take one extra step |

## How to test

1. Put a 7-segment display on `uo[0]` to `uo[7]` (segments A to G, then the
   decimal point).
2. Set EN (`ui[3]`) to 1 and SEL (`uio[5:4]`) to 0, the lowest digit.
3. Pull `rst_n` low for a moment, then release it. The display shows 0.
4. Apply a slow clock to `clk` (about 1 Hz) or press a push button. The display
   counts 0, 1, ... 9, A, b, C, d, E, F and wraps to 0. The decimal point
   lights at F.
5. Change SEL: the display shows the next digit, which steps once each time
   the digit below it wraps.
6. Set EN to 0: all digits stop.

Then, over SPI, with `clk` stopped low:

| Write | Effect |
|-------|--------|
| 0x00 = 0x6A, 0x01 = 0x3A, 0x09 = 0x04 | a 24-hour clock |
| 0x05 = 0x59, 0x06 = 0x23 | the count is 23:59; the next step gives 00:00 |
| 0x02 = 0x54 | a 0 on the three upper digits is left blank |
| 0x04 = 0x01 | INC and DEC count, `clk` does not |
| 0x04 = 0x03 | INC and DEC count, `clk` scans the digits, and DIG0 to DIG3 pick the digit |

A read of 0x85 and 0x86 returns the count.

## External hardware

A 7-segment display on `uo[0]` to `uo[7]` (active high), a switch for EN
(`ui[3]`), push buttons for INC and DEC (`ui[4]`, `ui[5]`), switches for SEL
(`uio[4]`, `uio[5]`; outputs in count modes 2 and 3), an SPI controller (for
example the RP2040 on the demo board) on `ui[0]`, `ui[1]`, `ui[2]` and
`uio[2]`, and a slow clock source or a push button on `clk`. CARRY and BORROW
(`uio[1]`, `uio[0]`) can enable a further counter.

For a four-digit multiplexed display, set the count mode to 2 or 3 and put
the four digits' segment pins in parallel on `uo[0]` to `uo[7]`. Mode 2: a
2-to-4 decoder on `uio[5:4]` picks the digit common. Mode 3: wire `uio[4]` to
`uio[7]` straight to the digit commons, 0 to 3 (through transistors if the
segments draw more than the pins give).
