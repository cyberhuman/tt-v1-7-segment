# SPDX-FileCopyrightText: © 2026 Raman Varabets
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, Timer

# Segment patterns {g,f,e,d,c,b,a} for the digits 0..F
PATTERNS = [0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07,
            0x7F, 0x6F, 0x77, 0x7C, 0x39, 0x5E, 0x79, 0x71]


def ui(en, sel):
    # ui_in bit 0 is EN, bits 2:1 are SEL. The base is written over SPI.
    return en | (sel << 1)


# SPI pins on uio_in: bit 0 CS (active low), bit 1 MOSI, bit 3 SCK
CS, MOSI, SCK = 0x01, 0x02, 0x08
SPI_HALF = 100  # ns, half of one SCK period


# Register addresses
BASE10, BASE32, PAD = 0x00, 0x01, 0x02


async def spi_clock_bits(dut, value, bits):
    # Send the top `bits` bits of a 16-bit value, MSB first, mode 0. CS must
    # already be low. MOSI changes while SCK is low and is sampled on the
    # rising edge.
    for i in range(bits):
        bit = (value >> (15 - i)) & 1
        dut.uio_in.value = bit * MOSI
        await Timer(SPI_HALF, unit="ns")
        dut.uio_in.value = bit * MOSI | SCK
        await Timer(SPI_HALF, unit="ns")
        dut.uio_in.value = bit * MOSI


async def spi_writes(dut, *writes, bits=16):
    # Several (address, value) writes in one CS-low period, CS idle high.
    # `bits` below 16 cuts the last write short (its first bits are sent).
    # One write takes 3.2 us, so a few fit between clock edges (5 us).
    dut.uio_in.value = 0            # CS low, SCK low
    await Timer(SPI_HALF, unit="ns")
    for n, (address, value) in enumerate(writes):
        last = n == len(writes) - 1
        await spi_clock_bits(dut, address << 8 | value, bits if last else 16)
    await Timer(SPI_HALF, unit="ns")
    dut.uio_in.value = CS           # CS back high
    await Timer(SPI_HALF, unit="ns")


async def spi_write(dut, address, value, bits=16):
    # One 16-bit write with its own CS pulse: address byte, then data byte
    await spi_writes(dut, (address, value), bits=bits)


async def write_settings(dut, base=0, pad=0):
    # Write the bases and the pad bits. base is one number for all digits, or
    # a list of four (digit 0 first); pad is the 4 pad bits (bit n is digit n).
    bases = list(base) if isinstance(base, (list, tuple)) else [base] * 4
    assert len(bases) == 4
    await spi_writes(dut,
                     (BASE10, (bases[1] & 0xF) << 4 | bases[0] & 0xF),
                     (BASE32, (bases[3] & 0xF) << 4 | bases[2] & 0xF),
                     (PAD, pad & 0xF))


async def start(dut, en, sel=0, base=None, pad=0):
    # Start the clock, hold reset for a few cycles, then release it.
    # base is one number for all digits, or a list of four (digit 0 first).
    # pad is the 4 pad bits (bit n is digit n), written with the bases.
    cocotb.start_soon(Clock(dut.clk, 10, unit="us").start())
    dut.ena.value = 1
    dut.ui_in.value = ui(en, sel)
    dut.uio_in.value = CS
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    # Look at the outputs on the falling edge, away from the rising edge
    await FallingEdge(dut.clk)
    # Reset clears the registers, so they are written after reset. EN is held
    # at 0 during the write and one clock cycle, so the count stays at 0.
    if base is not None or pad:
        dut.ui_in.value = ui(0, sel)
        await write_settings(dut, 0 if base is None else base, pad)
        await FallingEdge(dut.clk)
        dut.ui_in.value = ui(en, sel)


def shown(digit, co=0):
    # Expected uo_out: the pattern of the digit, CO as the top bit
    return PATTERNS[digit] | (0x80 if co else 0)


async def read_digits(dut, en=1):
    # Read all four digits (lowest first) by switching SEL, no clock edge needed
    values = []
    for sel in range(4):
        dut.ui_in.value = ui(en, sel)
        await Timer(1, unit="us")
        values.append(int(dut.uo_out.value) & 0x7F)
    return values


@cocotb.test()
async def test_reset(dut):
    await start(dut, 1)
    # Reset shows digit 0 on all four digits and CO is low
    for sel in range(4):
        dut.ui_in.value = ui(1, sel)
        await Timer(1, unit="us")
        assert dut.uo_out.value == PATTERNS[0], f"digit {sel}"


@cocotb.test()
async def test_count_and_carry(dut):
    await start(dut, 1)
    # Two full rounds of the lowest digit: every digit in order, CO only at F
    for i in range(32):
        digit = i % 16
        assert dut.uo_out.value == shown(digit, digit == 15), f"step {i}"
        await FallingEdge(dut.clk)


@cocotb.test()
async def test_hold(dut):
    await start(dut, 1)
    # Count to each digit, then stop with EN = 0: value holds and CO is 0
    for digit in range(16):
        assert dut.uo_out.value == shown(digit, digit == 15)
        dut.ui_in.value = ui(0, 0)
        await FallingEdge(dut.clk)
        for _ in range(4):
            assert dut.uo_out.value == PATTERNS[digit], f"hold at {digit}"
            await FallingEdge(dut.clk)
        dut.ui_in.value = ui(1, 0)
        await FallingEdge(dut.clk)


@cocotb.test()
async def test_sel_no_clock(dut):
    await start(dut, 1)
    # Count to 0x0035, then stop the clock edges from mattering: EN = 0
    for _ in range(0x35):
        await FallingEdge(dut.clk)
    dut.ui_in.value = ui(0, 0)
    await FallingEdge(dut.clk)
    # Changing SEL changes the display at once, within the same clock phase
    for sel, digit in [(0, 5), (1, 3), (2, 0), (3, 0), (1, 3), (0, 5)]:
        dut.ui_in.value = ui(0, sel)
        await Timer(1, unit="us")
        assert dut.uo_out.value == PATTERNS[digit], f"sel {sel}"


@cocotb.test()
async def test_carry_chain(dut):
    await start(dut, 1)
    # Counter is 0x0000 now. Each step the 16-bit value is one more.
    # digit1 steps exactly when digit0 goes F -> 0.
    for n in range(0, 0x120):
        values = await read_digits(dut)
        expected = [(n >> (4 * d)) & 0xF for d in range(4)]
        assert values == [PATTERNS[e] for e in expected], f"count {n:04X}"
        dut.ui_in.value = ui(1, 0)
        await FallingEdge(dut.clk)
    # 0x0120 reached: digit2 stepped once when 0x00FF went to 0x0100


@cocotb.test()
async def test_en_holds_all(dut):
    await start(dut, 1)
    for _ in range(0x1F):
        await FallingEdge(dut.clk)
    dut.ui_in.value = ui(0, 0)
    await FallingEdge(dut.clk)
    before = await read_digits(dut, en=0)
    assert before == [PATTERNS[0xF], PATTERNS[1], PATTERNS[0], PATTERNS[0]]
    await ClockCycles(dut.clk, 40)
    assert await read_digits(dut, en=0) == before


@cocotb.test()
async def test_co_of_shown_digit(dut):
    await start(dut, 1)
    # Run to 0x00EF: digit0 = F, digit1 = E. CO of digit0 is high, of digit1 low.
    for _ in range(0xEF):
        await FallingEdge(dut.clk)
    for sel, digit, co in [(0, 0xF, 1), (1, 0xE, 0), (2, 0, 0), (3, 0, 0)]:
        dut.ui_in.value = ui(1, sel)
        await Timer(1, unit="us")
        assert dut.uo_out.value == shown(digit, co), f"sel {sel}"
    # Step to 0x00FF: now digit1 has CO too, digit2 and digit3 do not
    for _ in range(0x10):
        await FallingEdge(dut.clk)
    for sel, digit, co in [(0, 0xF, 1), (1, 0xF, 1), (2, 0, 0), (3, 0, 0)]:
        dut.ui_in.value = ui(1, sel)
        await Timer(1, unit="us")
        assert dut.uo_out.value == shown(digit, co), f"sel {sel}"
    # With EN = 0 all CO are low
    dut.ui_in.value = ui(0, 1)
    await Timer(1, unit="us")
    assert dut.uo_out.value == PATTERNS[0xF]


@cocotb.test()
async def test_base10_digit0(dut):
    await start(dut, 1, base=10)
    # Lowest digit shows 0..9 then 0, never A..F, CO high only while it shows 9
    for i in range(25):
        digit = i % 10
        assert dut.uo_out.value == shown(digit, digit == 9), f"step {i}"
        await FallingEdge(dut.clk)


@cocotb.test()
async def test_base10_count_100(dut):
    await start(dut, 1, base=10)
    # Each step the decimal value is one more, digit1 steps when digit0 wraps
    for n in range(105):
        values = await read_digits(dut)
        expected = [(n // 10 ** d) % 10 for d in range(4)]
        assert values == [PATTERNS[e] for e in expected], f"count {n}"
        dut.ui_in.value = ui(1, 0)
        await FallingEdge(dut.clk)
    # 105 reached: digit2 stepped once when 99 went to 100


@cocotb.test()
async def test_base3(dut):
    await start(dut, 1, base=3)
    # Digit0 cycles 0, 1, 2, CO only at 2; the carry reaches digit1 after 3 clocks
    for n in range(10):
        values = await read_digits(dut)
        expected = [(n // 3 ** d) % 3 for d in range(4)]
        assert values == [PATTERNS[e] for e in expected], f"count {n}"
        dut.ui_in.value = ui(1, 0)
        await Timer(1, unit="us")
        assert dut.uo_out.value == shown(n % 3, n % 3 == 2), f"co at {n}"
        await FallingEdge(dut.clk)


@cocotb.test()
async def test_base_en_holds(dut):
    await start(dut, 1, base=10)
    # Count to 17, then EN = 0 with base 10 holds all digits
    for _ in range(17):
        await FallingEdge(dut.clk)
    before = await read_digits(dut, en=0)
    assert before == [PATTERNS[7], PATTERNS[1], PATTERNS[0], PATTERNS[0]]
    await ClockCycles(dut.clk, 25)
    assert await read_digits(dut, en=0) == before
    dut.ui_in.value = ui(0, 0)
    await Timer(1, unit="us")
    assert dut.uo_out.value == PATTERNS[7], "CO low with EN = 0"


async def read_base(dut):
    # Count with EN = 1 until the lowest digit wraps to 0 and return the
    # digit before it: base - 1 (15 when the base is 16)
    dut.ui_in.value = ui(1, 0)
    last = None
    for _ in range(17):
        await FallingEdge(dut.clk)
        value = int(dut.uo_out.value) & 0x7F
        if value == PATTERNS[0]:
            return PATTERNS.index(last)
        last = value
    return 15


@cocotb.test()
async def test_base_default_16(dut):
    await start(dut, 1)
    # No write after reset: the base is 16, the lowest digit counts to F
    assert await read_base(dut) == 15


async def read_settings(dut, clocks=400):
    # Read the settings back through the display: count with EN = 1 for more
    # than one full cycle and look at all four digits each clock. The base of
    # a digit is the highest value it reaches + 1; its pad bit is set if it
    # is ever blank. Only meaningful when every base is 2..4 (so the whole
    # cycle is short). Returns (bases of digit 0..3, pad).
    highest = [0] * 4
    pad = 0
    for _ in range(clocks):
        for d, v in enumerate(await read_digits(dut)):
            if v == 0:
                pad |= 1 << d
            else:
                highest[d] = max(highest[d], PATTERNS.index(v))
        dut.ui_in.value = ui(1, 0)
        await FallingEdge(dut.clk)
    return [h + 1 for h in highest], pad


# Settings every register test starts from: all bases 2 and pad 0b0101. The
# tests only raise bases, so the running count never ends up above a base.
PRESET = ([2, 2, 2, 2], 0b0101)


async def start_preset(dut):
    await start(dut, 0, base=PRESET[0], pad=PRESET[1])
    assert await read_settings(dut) == PRESET


@cocotb.test()
async def test_write_base10_alone(dut):
    await start_preset(dut)
    await spi_write(dut, BASE10, 0x43)       # base1 = 4, base0 = 3
    assert await read_settings(dut) == ([3, 4, 2, 2], 0b0101)


@cocotb.test()
async def test_write_base32_alone(dut):
    await start_preset(dut)
    await spi_write(dut, BASE32, 0x43)       # base3 = 4, base2 = 3
    assert await read_settings(dut) == ([2, 2, 3, 4], 0b0101)


@cocotb.test()
async def test_write_pad_alone(dut):
    await start_preset(dut)
    await spi_write(dut, PAD, 0xFA)          # upper 4 bits unused, pad = 1010
    assert await read_settings(dut) == ([2, 2, 2, 2], 0b1010)


@cocotb.test()
async def test_nibble_order(dut):
    # In BASE10 and BASE32 the higher digit is in the upper nibble
    await start(dut, 0, base=1)
    await spi_write(dut, BASE10, 0x42)       # base1 = 4, base0 = 2
    await spi_write(dut, BASE32, 0x32)       # base3 = 3, base2 = 2
    assert await read_settings(dut) == ([2, 4, 2, 3], 0)


@cocotb.test()
async def test_two_writes_one_cs_low(dut):
    await start_preset(dut)
    await spi_writes(dut, (BASE10, 0x33), (PAD, 0x03))
    assert await read_settings(dut) == ([3, 3, 2, 2], 0b0011)
    # Three in a row, the last one to the same register wins
    await spi_writes(dut, (BASE32, 0x43), (BASE10, 0x33), (BASE10, 0x44))
    assert await read_settings(dut) == ([4, 4, 3, 4], 0b0011)


@cocotb.test()
async def test_cut_short_write_ignored(dut):
    await start_preset(dut)
    for bits in (8, 15):
        # An address and data that would change everything, cut short
        await spi_write(dut, BASE10, 0x43, bits=bits)
        await spi_write(dut, PAD, 0x0F, bits=bits)
        assert await read_settings(dut) == PRESET, f"{bits} bits"
    # A cut-short write does not leave bits behind: a full write still works
    await spi_write(dut, BASE10, 0x43)
    assert await read_settings(dut) == ([3, 4, 2, 2], 0b0101)


@cocotb.test()
async def test_cut_short_then_full_same_cs(dut):
    await start_preset(dut)
    # 8 bits, CS high, then a full write: the 8 bits are not carried over
    await spi_write(dut, BASE32, 0x33, bits=8)
    await spi_write(dut, PAD, 0x0A)
    assert await read_settings(dut) == ([2, 2, 2, 2], 0b1010)


@cocotb.test()
async def test_read_bit_set_ignored(dut):
    await start_preset(dut)
    for address in (0x80 | BASE10, 0x80 | BASE32, 0x80 | PAD, 0xFF):
        await spi_write(dut, address, 0x33)
    assert await read_settings(dut) == PRESET


@cocotb.test()
async def test_unused_address_ignored(dut):
    await start_preset(dut)
    for address in (0x03, 0x04, 0x10, 0x7F):
        await spi_write(dut, address, 0x33)
    assert await read_settings(dut) == PRESET
    # The address is decoded in full: a register address with a high bit set
    for address in (0x40 | BASE10, 0x20 | PAD, 0x10 | BASE32):
        await spi_write(dut, address, 0x33)
    assert await read_settings(dut) == PRESET


@cocotb.test()
async def test_spi_cs_high_ignored(dut):
    await start_preset(dut)
    # SCK edges with CS high: two full writes worth of clocks, valid writes
    for value in (BASE10 << 8 | 0x43, PAD << 8 | 0x0F):
        for i in range(16):
            bit = (value >> (15 - i)) & 1
            dut.uio_in.value = CS | bit * MOSI | SCK
            await Timer(SPI_HALF, unit="ns")
            dut.uio_in.value = CS | bit * MOSI
            await Timer(SPI_HALF, unit="ns")
    assert await read_settings(dut) == PRESET


@cocotb.test()
async def test_clock_10_6_10_6(dut):
    await start(dut, 1, base=[10, 6, 10, 6])
    # A clock 00:00 to 59:59 then back to 00:00 (3600 steps, plus two more)
    for n in range(3602):
        values = await read_digits(dut)
        m = n % 3600
        expected = [m % 10, m // 10 % 6, m // 60 % 10, m // 600 % 6]
        assert values == [PATTERNS[e] for e in expected], f"count {n}"
        dut.ui_in.value = ui(1, 0)
        await FallingEdge(dut.clk)
    # Seconds just rolled: 59 -> 1:00 was passed at n = 59 -> 60 above


async def step(dut, n=1):
    # n clock cycles with EN = 1
    dut.ui_in.value = ui(1, 0)
    for _ in range(n):
        await FallingEdge(dut.clk)


@cocotb.test()
async def test_pad_blank_leading(dut):
    await start(dut, 1, base=10, pad=0b1110)
    # 0000: digit 0 is not padded and shows 0, digits 1..3 are blank
    assert await read_digits(dut) == [PATTERNS[0], 0, 0, 0]
    await step(dut, 5)
    # 0005: digit 0 lit, digits 1..3 blank
    assert await read_digits(dut) == [PATTERNS[5], 0, 0, 0]
    await step(dut, 100)
    # 0105: digit 1 is a 0 that is not leading and shows, digit 3 is blank
    assert await read_digits(dut) == [PATTERNS[5], PATTERNS[0], PATTERNS[1], 0]
    await step(dut, 899)
    # 1004: digit 3 is not 0, so nothing is blank
    assert await read_digits(dut) == [PATTERNS[4], PATTERNS[0], PATTERNS[0], PATTERNS[1]]


@cocotb.test()
async def test_pad_blank_all(dut):
    await start(dut, 1, base=10, pad=0b1111)
    # 0000 is all blank, 0001 shows the 1 only
    assert await read_digits(dut) == [0, 0, 0, 0]
    await step(dut)
    assert await read_digits(dut) == [PATTERNS[1], 0, 0, 0]


@cocotb.test()
async def test_pad_with_base_16(dut):
    # Bases 0 (= 16) with all pad bits: 0000 blank, 0010 keeps digit 0 lit
    await start(dut, 1, pad=0b1111)
    assert await read_digits(dut) == [0, 0, 0, 0]
    await step(dut, 16)
    assert await read_digits(dut) == [PATTERNS[0], PATTERNS[1], 0, 0]


@cocotb.test()
async def test_pad_bit_clear_keeps_zero(dut):
    # Pad bits on digits 3 and 1 only: digit 2 keeps its 0, digit 1 is blank
    # while digits 2 and 3 are 0 (digit 2 is, so blank)
    await start(dut, 1, base=10, pad=0b1010)
    assert await read_digits(dut) == [PATTERNS[0], 0, PATTERNS[0], 0]
    await step(dut, 100)
    # 0100: digit 2 is 1, so digit 1 (a 0 that is not leading) shows
    assert await read_digits(dut) == [PATTERNS[0], PATTERNS[0], PATTERNS[1], 0]


@cocotb.test()
async def test_pad_digit3_alone(dut):
    # Digit 3 depends only on itself: pad bit 3 blanks it while it is 0
    await start(dut, 1, base=10, pad=0b1000)
    await step(dut, 37)
    assert await read_digits(dut) == [PATTERNS[7], PATTERNS[3], PATTERNS[0], 0]


@cocotb.test()
async def test_pad_co_unchanged(dut):
    # Base 1 on digit 0: it stays 0 and CO is high with EN = 1. Digit 0 is
    # blank (pad bit set), CO still follows EN.
    await start(dut, 1, base=[1, 10, 10, 10], pad=0b1111)
    dut.ui_in.value = ui(1, 0)
    await Timer(1, unit="us")
    assert dut.uo_out.value == 0x80, "blank digit with CO high"
    dut.ui_in.value = ui(0, 0)
    await Timer(1, unit="us")
    assert dut.uo_out.value == 0x00, "blank digit with CO low"


@cocotb.test()
async def test_reset_clears_registers(dut):
    await start(dut, 1, base=[2, 3, 4, 2], pad=0b1111)
    assert await read_digits(dut) == [0, 0, 0, 0]
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 3)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)
    # Pad bits cleared: nothing is blank
    assert await read_digits(dut) == [PATTERNS[0]] * 4
    # All bases are 16: after 16**3 clocks the count is 1000, not earlier
    await step(dut, 0x1000 - 1)
    assert await read_digits(dut) == [PATTERNS[15]] * 3 + [PATTERNS[0]]
    await step(dut)
    assert await read_digits(dut) == [PATTERNS[0]] * 3 + [PATTERNS[1]]
