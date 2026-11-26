# SPDX-FileCopyrightText: © 2026 Raman Varabets
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge, Timer

# Segment patterns {g,f,e,d,c,b,a} for the digits 0..F
MINUS = 0x40  # segment G only
PATTERNS = [0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07,
            0x7F, 0x6F, 0x77, 0x7C, 0x39, 0x5E, 0x79, 0x71]


# SPI pins on uio_in: bit 0 CS (active low), bit 1 MOSI, bit 3 SCK.
# SEL is on uio_in bits 5:4 (SEL0 on bit 4). The base is written over SPI.
CS, MOSI, SCK = 0x01, 0x02, 0x08
SEL_SHIFT = 4

# The SEL value now on the pins. Every write to uio_in goes through uio_set,
# which adds it, so an SPI write never disturbs SEL and a SEL change never
# disturbs the SPI lines.
sel_now = 0
spi_now = CS  # the SPI lines now on the pins


def uio_set(dut, spi):
    # Drive uio_in: the SPI lines in bits 3:0 and SEL in bits 5:4
    global spi_now
    spi_now = spi
    dut.uio_in.value = spi | (sel_now << SEL_SHIFT)


def set_sel(dut, sel):
    # Change SEL only, the SPI lines keep their level
    global sel_now
    sel_now = sel
    uio_set(dut, spi_now)


# INC is on ui_in bit 1. Like SEL it keeps its level when EN is driven.
INC_BIT = 0x02
inc_now = 0
en_now = 0  # EN last driven


def set_inc(dut, level):
    # Change INC only, EN keeps its level
    global inc_now
    inc_now = level
    dut.ui_in.value = en_now | level * INC_BIT


def drive(dut, en, sel):
    # ui_in bit 0 is EN, bit 1 is INC; SEL goes to uio_in bits 5:4
    global en_now
    en_now = en
    dut.ui_in.value = en | inc_now * INC_BIT
    set_sel(dut, sel)
SPI_HALF = 100  # ns, half of one SCK period


# Register addresses
BASE10, BASE32, MODE, DOT, CTRL, COUNT10, COUNT32 = 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06

# CTRL bits: 1:0 are the count mode (0 clk, 1 to 3 INC), bit 2 counts down, 7:3 unused
DOWN = 0x04

# DOT values of one digit, and the register value after reset (CO everywhere)
DOT_OFF, DOT_ON, DOT_CO, DOT_NCO = 0, 1, 2, 3
DOT_RESET = 0xAA


async def spi_clock_bits(dut, value, bits):
    # Send the top `bits` bits of a 16-bit value, MSB first, mode 0. CS must
    # already be low. MOSI changes while SCK is low and is sampled on the
    # rising edge.
    for i in range(bits):
        bit = (value >> (15 - i)) & 1
        uio_set(dut, bit * MOSI)
        await Timer(SPI_HALF, unit="ns")
        uio_set(dut, bit * MOSI | SCK)
        await Timer(SPI_HALF, unit="ns")
        uio_set(dut, bit * MOSI)


async def spi_writes(dut, *writes, bits=16):
    # Several (address, value) writes in one CS-low period, CS idle high.
    # `bits` below 16 cuts the last write short (its first bits are sent).
    # One write takes 3.2 us, so a few fit between clock edges (5 us).
    uio_set(dut, 0)                # CS low, SCK low
    await Timer(SPI_HALF, unit="ns")
    for n, (address, value) in enumerate(writes):
        last = n == len(writes) - 1
        await spi_clock_bits(dut, address << 8 | value, bits if last else 16)
    await Timer(SPI_HALF, unit="ns")
    uio_set(dut, CS)              # CS back high
    await Timer(SPI_HALF, unit="ns")


async def spi_write(dut, address, value, bits=16):
    # One 16-bit write with its own CS pulse: address byte, then data byte
    await spi_writes(dut, (address, value), bits=bits)


async def write_settings(dut, base=0, mode=0, dot=DOT_RESET, ctrl=0):
    # Write the bases and the modes. base is one number for all digits, or a
    # list of four (digit 0 first); mode is the MODE register value (2 bits
    # per digit, digit 0 in bits 1:0); dot is the DOT register value in the
    # same layout, written only when it differs from the reset value; ctrl is
    # the CTRL register value, written only when it is not 0.
    bases = list(base) if isinstance(base, (list, tuple)) else [base] * 4
    assert len(bases) == 4
    await spi_writes(dut,
                     (BASE10, (bases[1] & 0xF) << 4 | bases[0] & 0xF),
                     (BASE32, (bases[3] & 0xF) << 4 | bases[2] & 0xF),
                     (MODE, mode & 0xFF),
                     *([(DOT, dot & 0xFF)] if dot != DOT_RESET else []),
                     *([(CTRL, ctrl & 0xFF)] if ctrl else []))


async def start(dut, en, sel=0, base=None, mode=0, dot=DOT_RESET, ctrl=0):
    # Start the clock, hold reset for a few cycles, then release it.
    # base is one number for all digits, or a list of four (digit 0 first).
    # mode, dot and ctrl are the MODE, DOT and CTRL register values, written
    # with the bases.
    cocotb.start_soon(Clock(dut.clk, 10, unit="us").start())
    dut.ena.value = 1
    global inc_now
    inc_now = 0
    drive(dut, en, sel)
    uio_set(dut, CS)
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    # Look at the outputs on the falling edge, away from the rising edge
    await FallingEdge(dut.clk)
    # Reset clears the registers, so they are written after reset. EN is held
    # at 0 during the write and one clock cycle, so the count stays at 0.
    if base is not None or mode or dot != DOT_RESET or ctrl:
        drive(dut, 0, sel)
        await write_settings(dut, 0 if base is None else base, mode, dot, ctrl)
        await FallingEdge(dut.clk)
        drive(dut, en, sel)


def shown(digit, co=0):
    # Expected uo_out: the pattern of the digit, CO as the top bit
    return PATTERNS[digit] | (0x80 if co else 0)


async def read_digits(dut, en=1):
    # Read all four digits (lowest first) by switching SEL, no clock edge needed
    values = []
    for sel in range(4):
        drive(dut, en, sel)
        await Timer(1, unit="us")
        values.append(int(dut.uo_out.value) & 0x7F)
    return values


@cocotb.test()
async def test_reset(dut):
    await start(dut, 1)
    # Reset shows digit 0 on all four digits and CO is low
    for sel in range(4):
        drive(dut, 1, sel)
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
        drive(dut, 0, 0)
        await FallingEdge(dut.clk)
        for _ in range(4):
            assert dut.uo_out.value == PATTERNS[digit], f"hold at {digit}"
            await FallingEdge(dut.clk)
        drive(dut, 1, 0)
        await FallingEdge(dut.clk)


@cocotb.test()
async def test_sel_no_clock(dut):
    await start(dut, 1)
    # Count to 0x0035, then stop the clock edges from mattering: EN = 0
    for _ in range(0x35):
        await FallingEdge(dut.clk)
    drive(dut, 0, 0)
    await FallingEdge(dut.clk)
    # Changing SEL changes the display at once, within the same clock phase
    for sel, digit in [(0, 5), (1, 3), (2, 0), (3, 0), (1, 3), (0, 5)]:
        drive(dut, 0, sel)
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
        drive(dut, 1, 0)
        await FallingEdge(dut.clk)
    # 0x0120 reached: digit2 stepped once when 0x00FF went to 0x0100


@cocotb.test()
async def test_en_holds_all(dut):
    await start(dut, 1)
    for _ in range(0x1F):
        await FallingEdge(dut.clk)
    drive(dut, 0, 0)
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
        drive(dut, 1, sel)
        await Timer(1, unit="us")
        assert dut.uo_out.value == shown(digit, co), f"sel {sel}"
    # Step to 0x00FF: now digit1 has CO too, digit2 and digit3 do not
    for _ in range(0x10):
        await FallingEdge(dut.clk)
    for sel, digit, co in [(0, 0xF, 1), (1, 0xF, 1), (2, 0, 0), (3, 0, 0)]:
        drive(dut, 1, sel)
        await Timer(1, unit="us")
        assert dut.uo_out.value == shown(digit, co), f"sel {sel}"
    # With EN = 0 all CO are low
    drive(dut, 0, 1)
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
        drive(dut, 1, 0)
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
        drive(dut, 1, 0)
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
    drive(dut, 0, 0)
    await Timer(1, unit="us")
    assert dut.uo_out.value == PATTERNS[7], "CO low with EN = 0"


async def read_base(dut):
    # Count with EN = 1 until the lowest digit wraps to 0 and return the
    # digit before it: base - 1 (15 when the base is 16)
    drive(dut, 1, 0)
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
    # than one full cycle and look at all four digits each clock. Only
    # meaningful when every base is 2..4 (so the whole cycle is short).
    # Returns (bases of digit 0..3, MODE value). A digit that is always blank
    # is mode 2, always a minus is mode 3, blank at some count is mode 1,
    # else mode 0. The base of a digit in mode 2 or 3 cannot be seen: None.
    # Otherwise it is the highest value the digit reaches + 1.
    seen = [set() for _ in range(4)]
    highest = [0] * 4
    for _ in range(clocks):
        for d, v in enumerate(await read_digits(dut)):
            seen[d].add(v)
            if v in PATTERNS:
                highest[d] = max(highest[d], PATTERNS.index(v))
        drive(dut, 1, 0)
        await FallingEdge(dut.clk)
    bases, mode = [], 0
    for d in range(4):
        if seen[d] == {0}:
            m = 2
        elif seen[d] == {MINUS}:
            m = 3
        else:
            m = 1 if 0 in seen[d] else 0
        mode |= m << (2 * d)
        bases.append(None if m >= 2 else highest[d] + 1)
    return bases, mode


# Settings every register test starts from: all bases 2, modes 1, 0, 1, 0
# (digit 0 first). The tests only raise bases, so the running count never
# ends up above a base.
PRESET = ([2, 2, 2, 2], 0b00_01_00_01)


async def start_preset(dut):
    await start(dut, 0, base=PRESET[0], mode=PRESET[1])
    assert await read_settings(dut) == PRESET


@cocotb.test()
async def test_write_base10_alone(dut):
    await start_preset(dut)
    await spi_write(dut, BASE10, 0x43)       # base1 = 4, base0 = 3
    assert await read_settings(dut) == ([3, 4, 2, 2], PRESET[1])


@cocotb.test()
async def test_write_base32_alone(dut):
    await start_preset(dut)
    await spi_write(dut, BASE32, 0x43)       # base3 = 4, base2 = 3
    assert await read_settings(dut) == ([2, 2, 3, 4], PRESET[1])


@cocotb.test()
async def test_write_mode_alone(dut):
    await start_preset(dut)
    await spi_write(dut, MODE, 0x44)         # modes 0, 1, 0, 1
    assert await read_settings(dut) == ([2, 2, 2, 2], 0x44)
    await spi_write(dut, MODE, 0xE4)         # modes 0, 1, 2, 3
    assert await read_settings(dut) == ([2, 2, None, None], 0xE4)


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
    await spi_writes(dut, (BASE10, 0x33), (MODE, 0x05))
    assert await read_settings(dut) == ([3, 3, 2, 2], 0x05)
    # Three in a row, the last one to the same register wins
    await spi_writes(dut, (BASE32, 0x43), (BASE10, 0x33), (BASE10, 0x44))
    assert await read_settings(dut) == ([4, 4, 3, 4], 0x05)


@cocotb.test()
async def test_cut_short_write_ignored(dut):
    await start_preset(dut)
    for bits in (8, 15):
        # An address and data that would change everything, cut short
        await spi_write(dut, BASE10, 0x43, bits=bits)
        await spi_write(dut, MODE, 0x0F, bits=bits)
        assert await read_settings(dut) == PRESET, f"{bits} bits"
    # A cut-short write does not leave bits behind: a full write still works
    await spi_write(dut, BASE10, 0x43)
    assert await read_settings(dut) == ([3, 4, 2, 2], PRESET[1])


@cocotb.test()
async def test_cut_short_then_full_same_cs(dut):
    await start_preset(dut)
    # 8 bits, CS high, then a full write: the 8 bits are not carried over
    await spi_write(dut, BASE32, 0x33, bits=8)
    await spi_write(dut, MODE, 0x44)
    assert await read_settings(dut) == ([2, 2, 2, 2], 0x44)


@cocotb.test()
async def test_read_bit_set_ignored(dut):
    await start_preset(dut)
    for address in (0x80 | BASE10, 0x80 | BASE32, 0x80 | MODE, 0x80 | DOT, 0x80 | CTRL, 0xFF):
        await spi_write(dut, address, 0x33)
    assert await read_settings(dut) == PRESET


@cocotb.test()
async def test_unused_address_ignored(dut):
    await start_preset(dut)
    for address in (0x07, 0x08, 0x10, 0x7F):
        await spi_write(dut, address, 0x33)
    assert await read_settings(dut) == PRESET
    # The address is decoded in full: a register address with a high bit set
    for address in (0x40 | BASE10, 0x20 | MODE, 0x10 | BASE32):
        await spi_write(dut, address, 0x33)
    assert await read_settings(dut) == PRESET


@cocotb.test()
async def test_spi_cs_high_ignored(dut):
    await start_preset(dut)
    # SCK edges with CS high: two full writes worth of clocks, valid writes
    for value in (BASE10 << 8 | 0x43, MODE << 8 | 0x0F):
        for i in range(16):
            bit = (value >> (15 - i)) & 1
            uio_set(dut, CS | bit * MOSI | SCK)
            await Timer(SPI_HALF, unit="ns")
            uio_set(dut, CS | bit * MOSI)
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
        drive(dut, 1, 0)
        await FallingEdge(dut.clk)
    # Seconds just rolled: 59 -> 1:00 was passed at n = 59 -> 60 above


async def step(dut, n=1):
    # n clock cycles with EN = 1
    drive(dut, 1, 0)
    for _ in range(n):
        await FallingEdge(dut.clk)


async def lit(dut, sel):
    # uo_out[6:0] of one digit
    drive(dut, 1, sel)
    await Timer(1, unit="us")
    return int(dut.uo_out.value) & 0x7F


@cocotb.test()
async def test_mode1_blank_own_zero(dut):
    await start(dut, 1, base=10, mode=0x55)
    # 0000: every digit is 0 and blank
    assert await read_digits(dut) == [0, 0, 0, 0]
    await step(dut, 105)
    # 0105: digits 0 and 2 lit, digits 1 and 3 are 0 and blank (no chain)
    assert await read_digits(dut) == [PATTERNS[5], 0, PATTERNS[1], 0]


@cocotb.test()
async def test_mode1_follows_count(dut):
    await start(dut, 1, base=10, mode=0x01)
    assert await lit(dut, 0) == 0
    await step(dut)
    assert await lit(dut, 0) == PATTERNS[1], "lit when it leaves 0"
    await step(dut, 9)
    assert await lit(dut, 0) == 0, "blank when it returns to 0"
    await step(dut, 3)
    assert await lit(dut, 0) == PATTERNS[3]


@cocotb.test()
async def test_mode2_blank(dut):
    await start(dut, 1, base=10, mode=0xAA)
    await step(dut, 37)
    assert await read_digits(dut) == [0, 0, 0, 0]


@cocotb.test()
async def test_mode3_minus(dut):
    await start(dut, 1, base=10, mode=0xFF)
    for _ in range(3):
        # 0000 first, then non-zero counts
        assert await read_digits(dut) == [MINUS] * 4
        await step(dut, 7)
    await step(dut, 100)
    assert await read_digits(dut) == [MINUS] * 4


@cocotb.test()
async def test_modes_differ_per_digit(dut):
    # Digit 0 mode 3, digit 1 mode 2, digit 2 mode 1, digit 3 mode 0
    await start(dut, 1, base=10, mode=0b00_01_10_11)
    assert await read_digits(dut) == [MINUS, 0, 0, PATTERNS[0]]
    await step(dut, 235)
    assert await read_digits(dut) == [MINUS, 0, PATTERNS[2], PATTERNS[0]]
    await step(dut, 765)
    # 1000: digit 3 shows 1, digit 2 is 0 and blank
    assert await read_digits(dut) == [MINUS, 0, 0, PATTERNS[1]]
    # The other way round: digit 0 mode 0, 1 mode 1, 2 mode 2, 3 mode 3
    await start(dut, 1, base=10, mode=0b11_10_01_00)
    await step(dut, 1)
    assert await read_digits(dut) == [PATTERNS[1], 0, 0, MINUS]


@cocotb.test()
async def test_co_same_in_all_modes(dut):
    # Base 1 on digit 0: it stays 0 and CO is high with EN = 1
    for m in range(4):
        await start(dut, 1, base=[1, 10, 10, 10], mode=m * 0x55)
        for en, co in ((1, 0x80), (0, 0)):
            drive(dut, en, 0)
            await Timer(1, unit="us")
            assert int(dut.uo_out.value) & 0x80 == co, f"mode {m} en {en}"
        dut.rst_n.value = 0
        await ClockCycles(dut.clk, 2)
        dut.rst_n.value = 1


@cocotb.test()
async def test_mode_does_not_disturb_count(dut):
    await start(dut, 1, base=10, mode=0)
    await step(dut, 3)
    await spi_write(dut, MODE, 0x02)         # digit 0 to mode 2
    await step(dut, 4)
    assert await lit(dut, 0) == 0
    await spi_write(dut, MODE, 0x00)         # still before the next clock edge
    assert int(dut.uo_out.value) & 0x7F == PATTERNS[7]


@cocotb.test()
async def test_reset_clears_registers(dut):
    await start(dut, 1, base=[2, 3, 4, 2], mode=0xFF)
    assert await read_digits(dut) == [MINUS] * 4
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 3)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)
    # Modes cleared: every digit is shown as is
    assert await read_digits(dut) == [PATTERNS[0]] * 4
    # All bases are 16: after 16**3 clocks the count is 1000, not earlier
    await step(dut, 0x1000 - 1)
    assert await read_digits(dut) == [PATTERNS[15]] * 3 + [PATTERNS[0]]
    await step(dut)
    assert await read_digits(dut) == [PATTERNS[0]] * 3 + [PATTERNS[1]]


async def dp(dut, sel):
    # uo_out[7] of one digit
    drive(dut, 1, sel)
    await Timer(1, unit="us")
    return int(dut.uo_out.value) >> 7


@cocotb.test()
async def test_dot_reset_is_co(dut):
    # After reset bit 7 is CO of each digit. Base 1 on digit 0 and 2 on
    # digit 1 (written with DOT left alone) give CO on digit 0 at once.
    await start(dut, 1, base=[1, 2, 2, 2])
    assert [await dp(dut, d) for d in range(4)] == [1, 0, 0, 0]
    await step(dut)
    assert [await dp(dut, d) for d in range(4)] == [1, 1, 0, 0]
    drive(dut, 0, 0)
    await Timer(1, unit="us")
    assert int(dut.uo_out.value) >> 7 == 0, "CO is low with EN = 0"


@cocotb.test()
async def test_dot_off_on(dut):
    # Digit 0 counts 0..3: off keeps bit 7 low and on keeps it high, also at 3
    for value, level in ((DOT_OFF, 0), (DOT_ON, 1)):
        await start(dut, 1, base=4, dot=value * 0x55)
        for i in range(10):
            assert await dp(dut, 0) == level, f"dot {value} step {i}"
            assert await lit(dut, 0) == PATTERNS[i % 4]
            await step(dut)


@cocotb.test()
async def test_dot_inverse_co(dut):
    await start(dut, 1, base=4, dot=0xFF)
    for i in range(10):
        assert await dp(dut, 0) == (0 if i % 4 == 3 else 1), f"step {i}"
        await step(dut)
    # With EN = 0 CO is low, so the inverse is high
    drive(dut, 0, 0)
    await Timer(1, unit="us")
    assert int(dut.uo_out.value) >> 7 == 1


async def dots(dut, en):
    # uo_out[7] of all four digits (lowest first) with the given EN
    values = []
    for sel in range(4):
        drive(dut, en, sel)
        await Timer(1, unit="us")
        values.append(int(dut.uo_out.value) >> 7)
    return values


@cocotb.test()
async def test_dot_differs_per_digit(dut):
    # Bases 1 make CO of every digit equal to EN. With digit 0 off, digit 1
    # on, digit 2 CO and digit 3 inverse CO, the pattern with EN = 1 and with
    # EN = 0 tells every digit apart, so each bit pair is checked through SEL.
    await start(dut, 1, base=1, dot=0b11_10_01_00)
    assert await dots(dut, 1) == [0, 1, 1, 0]
    assert await dots(dut, 0) == [0, 1, 0, 1]
    # The other way round: digit 0 inverse CO, 1 CO, 2 on, 3 off
    await start(dut, 1, base=1, dot=0b00_01_10_11)
    assert await dots(dut, 1) == [0, 1, 1, 0]
    assert await dots(dut, 0) == [1, 0, 1, 0]
    # A pair of the other digits is not mixed in: only digit 2 changes
    await start(dut, 1, base=1, dot=0b01_01_00_01)
    assert await dots(dut, 1) == [1, 0, 1, 1]
    assert await dots(dut, 0) == [1, 0, 1, 1]


@cocotb.test()
async def test_dot_off_keeps_carry(dut):
    # Dot off on every digit: the carry between the digits still works
    await start(dut, 1, base=[4, 3, 10, 10], dot=0)
    for n in range(40):
        values = await read_digits(dut)
        expected = [n % 4, n // 4 % 3, n // 12 % 10, 0]
        assert values == [PATTERNS[e] for e in expected], f"count {n}"
        assert await dots(dut, 1) == [0] * 4, f"count {n}"
        drive(dut, 1, 0)
        await FallingEdge(dut.clk)


@cocotb.test()
async def test_dot_alone(dut):
    await start_preset(dut)
    # Reset value: bit 7 is CO, low with EN = 0. Inverse of CO is high.
    assert await dots(dut, 0) == [0] * 4
    await spi_write(dut, DOT, 0xFF)
    assert await dots(dut, 0) == [1] * 4
    assert await read_settings(dut) == PRESET
    # The reverse: the other registers leave DOT alone
    await spi_write(dut, DOT, 0xE4)          # off, on, CO, inverse
    assert await dots(dut, 0) == [0, 1, 0, 1]
    await spi_write(dut, BASE10, 0x43)
    await spi_write(dut, BASE32, 0x43)
    await spi_write(dut, MODE, 0x44)
    assert await dots(dut, 0) == [0, 1, 0, 1]


@cocotb.test()
async def test_reset_returns_dot(dut):
    await start(dut, 1, dot=0xFF)
    assert await dots(dut, 0) == [1] * 4
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 3)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)
    assert await dots(dut, 0) == [0] * 4, "CO is low with EN = 0"
    # CO of digit 0 is high at F: the value is 0xAA, not 0x00
    await step(dut, 15)
    assert await dp(dut, 0) == 1


def after_down(n, bases):
    # The four digits (lowest first) after n steps down from 0000, with the
    # given bases (0 means 16): the value is the mixed-base number, modulo
    # the product of the bases.
    bases = [b or 16 for b in bases]
    total = bases[0] * bases[1] * bases[2] * bases[3]
    value = -n % total
    digits, weight = [], 1
    for b in bases:
        digits.append(value // weight % b)
        weight *= b
    return digits


async def check_digits(dut, digits, what, en=1):
    assert await read_digits(dut, en) == [PATTERNS[d] for d in digits], what


async def set_ctrl(dut, value):
    # Write CTRL with EN = 0, so no clock edge counts in the old direction
    # while the write is on its way, and stop at a falling edge
    drive(dut, 0, 0)
    await spi_write(dut, CTRL, value)
    await FallingEdge(dut.clk)


@cocotb.test()
async def test_down_base16(dut):
    await start(dut, 1, ctrl=DOWN)
    await check_digits(dut, [0, 0, 0, 0], "0000")
    await step(dut)
    await check_digits(dut, [15, 15, 15, 15], "FFFF")
    await step(dut)
    await check_digits(dut, [14, 15, 15, 15], "FFFE")
    for n in range(3, 0x130):
        await step(dut)
        await check_digits(dut, after_down(n, [0] * 4), f"step {n}")


@cocotb.test()
async def test_down_base10(dut):
    await start(dut, 1, base=10, ctrl=DOWN)
    await step(dut)
    await check_digits(dut, [9, 9, 9, 9], "9999")
    # From 0100 one step gives 0099
    await step(dut, 9899)
    await check_digits(dut, [0, 0, 1, 0], "0100")
    await step(dut)
    await check_digits(dut, [9, 9, 0, 0], "0099")


@cocotb.test()
async def test_down_clock(dut):
    await start(dut, 1, base=[10, 6, 10, 6], ctrl=DOWN)
    await step(dut)
    await check_digits(dut, [9, 5, 9, 5], "59:59")
    for n in range(2, 3601):
        await step(dut)
        await check_digits(dut, after_down(n, [10, 6, 10, 6]), f"step {n}")
    # 3600 steps down is a full round (checked above: back at 00:00), then
    # 59:59 again
    await step(dut)
    await check_digits(dut, [9, 5, 9, 5], "59:59 again")


@cocotb.test()
async def test_down_borrow_on_dot(dut):
    # DOT is CO after reset: counting down it shows the borrow
    await start(dut, 1, base=10, ctrl=DOWN)
    for n in range(130):
        digits = after_down(n, [10] * 4)
        expected = [int(all(d == 0 for d in digits[:i + 1])) for i in range(4)]
        assert await dots(dut, 1) == expected, f"step {n}"
        await step(dut)
    # With EN = 0 the borrow is low everywhere
    assert await dots(dut, 0) == [0] * 4
    # Counting down, a digit that is not 0 has no borrow, even at its base - 1
    await start(dut, 1, base=4, ctrl=DOWN)
    await step(dut)
    assert await dots(dut, 1) == [0] * 4, "0003 in base 4: no borrow"


@cocotb.test()
async def test_down_after_up_returns(dut):
    await start(dut, 1, base=[10, 6, 10, 6])
    await step(dut, 1234)
    before = await read_digits(dut)
    assert before == [PATTERNS[d] for d in [4, 3, 0, 2]], "1234 steps up"
    await set_ctrl(dut, DOWN)
    for n in range(1233, -1, -1):
        await step(dut)
        await check_digits(dut, [n % 10, n // 10 % 6, n // 60 % 10, n // 600 % 6], f"back at {n}")


@cocotb.test()
async def test_down_en_holds(dut):
    await start(dut, 1, base=10, ctrl=DOWN)
    await step(dut, 5)
    before = await read_digits(dut, en=0)
    assert before == [PATTERNS[d] for d in [5, 9, 9, 9]]
    await ClockCycles(dut.clk, 25)
    assert await read_digits(dut, en=0) == before
    assert await dots(dut, 0) == [0] * 4


@cocotb.test()
async def test_direction_switch_between_steps(dut):
    bases = [10, 6, 10, 6]
    await start(dut, 1, base=bases)
    value = 0                                # the mixed-base value, mod 3600
    # Up, down across the wrap below 0000, up again across it, down again
    for direction, steps in ((0, 7), (1, 20), (0, 15), (1, 8), (0, 40), (1, 3), (0, 1)):
        await set_ctrl(dut, DOWN if direction else 0)
        for _ in range(steps):
            await step(dut)
            value = (value + (-1 if direction else 1)) % 3600
            await check_digits(dut, [value % 10, value // 10 % 6, value // 60 % 10, value // 600 % 6],
                               f"direction {direction}")


@cocotb.test()
async def test_ctrl_reserved_bits_ignored(dut):
    await start_preset(dut)
    # Every value without bit 2 counts up, and changes no other register
    for value in (0x00, 0xF8):
        await spi_write(dut, CTRL, value)
        assert await read_settings(dut) == PRESET, f"CTRL {value:02X}"
    # Every value with bit 2 counts down, the same way
    for value in (0x04, 0xFC):
        await start(dut, 1, base=10)
        await spi_write(dut, CTRL, value)
        await step(dut)
        await check_digits(dut, [9, 9, 9, 9], f"CTRL {value:02X}")
        await step(dut)
        await check_digits(dut, [8, 9, 9, 9], f"CTRL {value:02X}")
        # Writing it again with other reserved bits changes nothing
        await set_ctrl(dut, 0xFC if value < 0xFC else 0x04)
        await step(dut)
        await check_digits(dut, [7, 9, 9, 9], f"CTRL {value:02X} again")


@cocotb.test()
async def test_ctrl_alone(dut):
    # Digit modes 1 (blank 0), bases 3, 4, 5, 6; dots off, on, CO, inverse CO
    await start(dut, 0, base=[3, 4, 5, 6], mode=0x55, dot=0b11_10_01_00)
    await spi_write(dut, CTRL, DOWN)
    await FallingEdge(dut.clk)
    for n in range(130):
        digits = after_down(n, [3, 4, 5, 6])
        zeros = [int(all(d == 0 for d in digits[:i + 1])) for i in range(4)]
        # All four digits with EN = 1 in one pass: segments and dot together
        out = []
        for sel in range(4):
            drive(dut, 1, sel)
            await Timer(1, unit="us")
            out.append(int(dut.uo_out.value))
        assert [o & 0x7F for o in out] == [0 if d == 0 else PATTERNS[d] for d in digits], f"step {n}"
        assert [o >> 7 for o in out] == [0, 1, zeros[2], 1 - zeros[3]], f"step {n}"
        await step(dut)
    # The other registers leave CTRL alone: still counting down
    drive(dut, 0, 0)
    await spi_writes(dut, (MODE, 0x00), (DOT, DOT_RESET), (BASE10, 0x43), (BASE32, 0x65))
    await FallingEdge(dut.clk)
    digits = after_down(130, [3, 4, 5, 6])
    await check_digits(dut, digits, "registers written")
    await step(dut)
    await check_digits(dut, after_down(131, [3, 4, 5, 6]), "still down")


@cocotb.test()
async def test_reset_returns_up(dut):
    await start(dut, 1, base=10, ctrl=DOWN)
    await step(dut, 3)
    await check_digits(dut, [7, 9, 9, 9], "down before reset")
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 3)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)
    await check_digits(dut, [0, 0, 0, 0], "after reset")
    await step(dut, 3)
    await check_digits(dut, [3, 0, 0, 0], "counts up after reset")
    # Bases are 16 again too
    await step(dut, 12)
    await check_digits(dut, [15, 0, 0, 0], "base 16")


async def load_reg(dut, *writes, en=1, bits=16):
    # Write count registers (address, value pairs) and wait for the loading
    # edge, stopping at the falling edge after it. The writes start just after
    # a rising edge and take at most 6.6 us, so they end before the next one.
    # EN is 0 until the writes begin, so the edge before them cannot count.
    # EN is `en` while they run, so the loading edge has that EN.
    drive(dut, 0, 0)
    await RisingEdge(dut.clk)
    await Timer(100, unit="ns")
    drive(dut, en, 0)
    await spi_writes(dut, *writes, bits=bits)
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)


async def write_count(dut, value, en=1):
    # Write both count registers (digits 3 and 2 in the high byte of the
    # 16-bit value) so that all four digits load on the same edge
    await load_reg(dut, (COUNT10, value & 0xFF), (COUNT32, value >> 8), en=en)


def digits_of(value):
    # The four hex digits of a 16-bit value, lowest first
    return [value >> s & 0xF for s in (0, 4, 8, 12)]


@cocotb.test()
async def test_count_loads_on_next_edge(dut):
    await start(dut, 0)
    # One write at a falling edge ends before the next rising edge
    await spi_write(dut, COUNT10, 0x34)
    await check_digits_one(dut, 0, 0, en=0)  # nothing changes before the edge
    # COUNT10 = 0x34: digit 1 is 3, digit 0 is 4; digits 3, 2 are untouched
    await check_digits(dut, [4, 3, 0, 0], "after the edge", en=0)
    await load_reg(dut, (COUNT32, 0x12), en=0)
    await check_digits(dut, [4, 3, 2, 1], "nibble order 1 2 3 4", en=0)


async def check_digits_one(dut, sel, digit, en=1):
    drive(dut, en, sel)
    await Timer(1, unit="us")
    assert int(dut.uo_out.value) & 0x7F == PATTERNS[digit], f"digit {sel}"


@cocotb.test()
async def test_count_both_registers_one_edge(dut):
    # EN = 0: the load happens anyway, all four digits on the same edge
    await start(dut, 0)
    await write_count(dut, 0x1234, en=0)
    await check_digits(dut, [4, 3, 2, 1], "loaded with EN = 0", en=0)
    for sel in range(4):
        drive(dut, 0, sel)
        await Timer(1, unit="us")
        assert int(dut.uo_out.value) & 0x7F == PATTERNS[[4, 3, 2, 1][sel]]
    await FallingEdge(dut.clk)
    await check_digits(dut, [4, 3, 2, 1], "EN = 0 holds after the load", en=0)


@cocotb.test()
async def test_load_edge_does_not_count(dut):
    await start(dut, 1)
    await write_count(dut, 0x1234)
    await check_digits(dut, [4, 3, 2, 1], "the loading edge does not count")
    await step(dut, 1)
    await check_digits(dut, [5, 3, 2, 1], "the edge after it counts")


@cocotb.test()
async def test_count10_alone_leaves_upper_digits(dut):
    await start(dut, 1)
    await write_count(dut, 0x1234)
    await step(dut, 1)
    # Digits 3, 2 get no carry from a digit that loads, so they hold
    await load_reg(dut, (COUNT10, 0xFF))
    await check_digits(dut, [15, 15, 2, 1], "digits 1, 0 load, 3, 2 hold")
    await step(dut, 1)
    # The next edge counts normally: F F wraps and carries up
    await check_digits(dut, [0, 0, 3, 1], "then all count")


@cocotb.test()
async def test_count32_alone_leaves_lower_digits_counting(dut):
    await start(dut, 1)
    await write_count(dut, 0x0003)
    await load_reg(dut, (COUNT32, 0x21))
    await check_digits(dut, [4, 0, 1, 2], "digits 3, 2 load, 1, 0 count")


@cocotb.test()
async def test_same_value_twice_loads_twice(dut):
    await start(dut, 1)
    await load_reg(dut, (COUNT10, 0x05))
    await check_digits(dut, [5, 0, 0, 0], "first load")
    await step(dut, 1)
    await check_digits(dut, [6, 0, 0, 0], "counted in between")
    await load_reg(dut, (COUNT10, 0x05))
    await check_digits(dut, [5, 0, 0, 0], "same value loads again")
    await step(dut, 1)
    await check_digits(dut, [6, 0, 0, 0], "no third load")


@cocotb.test()
async def test_load_base10_then_step(dut):
    await start(dut, 1, base=10)
    await write_count(dut, 0x0009)
    await check_digits(dut, [9, 0, 0, 0], "loaded 0009")
    await step(dut, 1)
    await check_digits(dut, [0, 1, 0, 0], "0010")


@cocotb.test()
async def test_load_then_step_down(dut):
    await start(dut, 1, base=10, ctrl=DOWN)
    await write_count(dut, 0x0100)
    await check_digits(dut, [0, 0, 1, 0], "loaded 0100")
    await step(dut, 1)
    await check_digits(dut, [9, 9, 0, 0], "0099")


@cocotb.test()
async def test_load_value_above_base_taken_as_is(dut):
    await start(dut, 1, base=10)
    await write_count(dut, 0x00AB)
    await check_digits(dut, [11, 10, 0, 0], "loaded as is")


@cocotb.test()
async def test_load_has_no_carry(dut):
    # Digit 0 is F (CO high) when a load of 3 is written: no carry into digit 1
    await start(dut, 1)
    await step(dut, 15)
    await check_digits(dut, [15, 0, 0, 0], "at F")
    await load_reg(dut, (COUNT10, 0x03))
    await check_digits(dut, [3, 0, 0, 0], "digit 1 did not step")
    # Loading F: CO is high after the edge, and digit 1 has not stepped
    await load_reg(dut, (COUNT10, 0x0F))
    assert int(dut.uo_out.value) == shown(15, 1), "dot is CO after loading F"
    await check_digits(dut, [15, 0, 0, 0], "loaded F")
    await step(dut, 1)
    await check_digits(dut, [0, 1, 0, 0], "carry on the edge after")
    # Digits 1 and 0 both F (carry into digit 2) and loading 0: digit 2 holds
    await load_reg(dut, (COUNT10, 0xFF))
    await load_reg(dut, (COUNT10, 0x00))
    await check_digits(dut, [0, 0, 0, 0], "digit 2 did not step")


@cocotb.test()
async def test_count_cut_short_write_ignored(dut):
    await start(dut, 1)
    await load_reg(dut, (COUNT10, 0x55), bits=15)
    await check_digits(dut, [1, 0, 0, 0], "counts, no load")
    await load_reg(dut, (COUNT10, 0x55), bits=8)
    await check_digits(dut, [2, 0, 0, 0], "counts, no load")


@cocotb.test()
async def test_reset_loads_nothing(dut):
    await start(dut, 0)
    await write_count(dut, 0x1234, en=0)
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 3)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)
    await check_digits(dut, [0, 0, 0, 0], "reset after a load", en=0)
    await FallingEdge(dut.clk)
    await check_digits(dut, [0, 0, 0, 0], "no load after reset", en=0)
    # A write that has not loaded yet is dropped by a reset too
    await spi_write(dut, COUNT10, 0x77)
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 3)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)
    await FallingEdge(dut.clk)
    await check_digits(dut, [0, 0, 0, 0], "write before reset not loaded", en=0)


@cocotb.test()
async def test_count_leaves_other_registers(dut):
    # bases 10 6 10 6, modes 0 3 2 1, dots ON OFF NCO ON, counting down
    await start(dut, 0, base=[10, 6, 10, 6], mode=0x6C, dot=0x71, ctrl=DOWN)
    await write_count(dut, 0x1234, en=0)
    expected = [shown(4) | 0x80, MINUS, 0x80, shown(1) | 0x80]
    for sel in range(4):
        drive(dut, 0, sel)
        await Timer(1, unit="us")
        assert int(dut.uo_out.value) == expected[sel], f"digit {sel}"
    # Writing another register loads nothing
    await spi_write(dut, MODE, 0x6C)
    await FallingEdge(dut.clk)
    await check_digits_one(dut, 0, 4, en=0)
    # Down is still on, and the bases are still 10 6 10 6
    drive(dut, 1, 0)
    await FallingEdge(dut.clk)
    assert await lit(dut, 0) == PATTERNS[3], "still counting down"
    await write_count(dut, 0x0000)
    await step(dut, 1)
    await check_digits_one(dut, 0, 9)
    await check_digits_one(dut, 3, 5)


@cocotb.test()
async def test_sel_change_between_writes_keeps_write(dut):
    # SEL changes between and during SPI writes must not corrupt a write
    await start(dut, 0, base=0)
    dut.ui_in.value = 0

    async def wiggle():
        for i in range(40):
            set_sel(dut, i % 4)
            await Timer(77, unit="ns")

    cocotb.start_soon(wiggle())
    await spi_writes(dut, (BASE10, 0x43), (BASE32, 0x43), (MODE, 0x54))
    await Timer(5, unit="us")
    set_sel(dut, 0)
    assert await read_settings(dut) == ([3, 4, 3, 4], 0x54)
    # Count too: the write above did not change anything else
    await write_count(dut, 0x2359, en=0)
    assert await read_digits(dut, en=0) == [PATTERNS[9], PATTERNS[5], PATTERNS[3], PATTERNS[2]]


@cocotb.test()
async def test_spi_does_not_change_sel(dut):
    # SPI traffic on uio_in[3:0] does not move SEL on uio_in[5:4]
    await start(dut, 0, base=0)
    await write_count(dut, 0x4321, en=0)
    for sel in range(4):
        set_sel(dut, sel)
        # a full write and a cut-short one, with SCK toggling the whole time
        await spi_write(dut, MODE, 0x00)
        await spi_write(dut, DOT, 0x00, bits=5)
        await Timer(1, unit="us")
        assert (int(dut.uio_in.value) >> 4) & 3 == sel
        assert int(dut.uo_out.value) & 0x7F == PATTERNS[(0x4321 >> (4 * sel)) & 0xF], f"sel {sel}"


@cocotb.test()
async def test_ui_in_2_1_select_nothing(dut):
    # ui_in[2:1] no longer select the digit: with SEL on the uio pins fixed
    # the display stays on that digit whatever ui_in[2:1] are
    await start(dut, 0, base=0)
    await write_count(dut, 0x4321, en=0)
    for sel in range(4):
        set_sel(dut, sel)
        for bits in range(4):
            dut.ui_in.value = bits << 1
            await Timer(1, unit="us")
            assert int(dut.uo_out.value) & 0x7F == PATTERNS[(0x4321 >> (4 * sel)) & 0xF], f"sel {sel} ui {bits}"
        # a SEL pin on ui_in[2:1] does not count either
    dut.ui_in.value = 0


# INC and the count mode (CTRL bits 1:0)

async def set_mode(dut, mode, ctrl=0):
    # Write CTRL = ctrl | mode at a falling edge of clk. The write ends in the
    # low half of the clock period, with INC low, so the switch makes no edge.
    drive(dut, 0, 0)
    await spi_write(dut, CTRL, ctrl | mode)


async def inc_pulses(dut, n=1, en=1):
    # n rising edges on INC, with EN = en. clk keeps running.
    drive(dut, en, 0)
    await Timer(200, unit="ns")  # EN settles before the first edge
    for _ in range(n):
        set_inc(dut, 1)
        await Timer(200, unit="ns")
        set_inc(dut, 0)
        await Timer(200, unit="ns")


async def start_mode(dut, mode, ctrl=0, base=None):
    # Reset, then the mode at a falling edge of clk
    await start(dut, 0, base=base)
    await set_mode(dut, mode, ctrl)
    await FallingEdge(dut.clk)


@cocotb.test()
async def test_inc_mode1_clk_does_not_count(dut):
    await start_mode(dut, 1)
    await step(dut, 10)
    await check_digits(dut, [0, 0, 0, 0], "clk in mode 1")
    await inc_pulses(dut, 5)
    await check_digits(dut, [5, 0, 0, 0], "5 INC edges")
    # The falling edge of INC does not count, nor does a level
    set_inc(dut, 1)
    await step(dut, 3)
    await check_digits(dut, [6, 0, 0, 0], "INC high, clk running")
    set_inc(dut, 0)
    await step(dut, 3)
    await check_digits(dut, [6, 0, 0, 0], "INC falls")


@cocotb.test()
async def test_inc_en_gates(dut):
    await start_mode(dut, 1)
    await inc_pulses(dut, 3, en=0)
    await check_digits(dut, [0, 0, 0, 0], "EN = 0", en=0)
    await inc_pulses(dut, 2, en=1)
    await check_digits(dut, [2, 0, 0, 0], "EN = 1")
    await inc_pulses(dut, 3, en=0)
    await check_digits(dut, [2, 0, 0, 0], "EN = 0 again", en=0)


@cocotb.test()
async def test_inc_ignored_in_mode0(dut):
    await start(dut, 1)
    # Between two clk edges: 5 INC edges and the digit is still 0
    await inc_pulses(dut, 5)
    assert await lit(dut, 0) == PATTERNS[0], "INC in mode 0"
    await step(dut, 2)
    assert await lit(dut, 0) == PATTERNS[2], "clk counts"
    await FallingEdge(dut.clk)
    await inc_pulses(dut, 5)
    assert await lit(dut, 0) == PATTERNS[3], "INC still ignored"


@cocotb.test()
async def test_inc_carry_across_digits(dut):
    await start_mode(dut, 1)
    await inc_pulses(dut, 16 * 16 + 17)
    await check_digits(dut, [1, 1, 1, 0], "carry over three digits")


@cocotb.test()
async def test_inc_wrap_16_bits(dut):
    await start_mode(dut, 1, ctrl=DOWN)
    await inc_pulses(dut, 1)
    await check_digits(dut, [15, 15, 15, 15], "0000 down to FFFF")
    await inc_pulses(dut, 17)
    await check_digits(dut, [14, 14, 15, 15], "down with borrow")


@cocotb.test()
async def test_inc_down(dut):
    await start_mode(dut, 1, ctrl=DOWN, base=[10, 6, 10, 6])
    await inc_pulses(dut, 1)
    await check_digits(dut, [9, 5, 9, 5], "00:00 down to 59:59")
    await inc_pulses(dut, 10)
    await check_digits(dut, [9, 4, 9, 5], "borrow")


@cocotb.test()
async def test_inc_base10(dut):
    await start_mode(dut, 1, base=10)
    await inc_pulses(dut, 9)
    await check_digits(dut, [9, 0, 0, 0], "9")
    await inc_pulses(dut, 1)
    await check_digits(dut, [0, 1, 0, 0], "wrap to 10")
    await inc_pulses(dut, 90)
    await check_digits(dut, [0, 0, 1, 0], "100")


@cocotb.test()
async def test_inc_count_loads_on_next_inc_edge(dut):
    await start_mode(dut, 1)
    await inc_pulses(dut, 2)
    await spi_write(dut, COUNT10, 0x34)
    await spi_write(dut, COUNT32, 0x12)
    # clk edges do not load
    await step(dut, 3)
    await check_digits(dut, [2, 0, 0, 0], "written, not loaded by clk", en=0)
    await inc_pulses(dut, 1)
    await check_digits(dut, [4, 3, 2, 1], "loaded, load edge does not count")
    await inc_pulses(dut, 1)
    await check_digits(dut, [5, 3, 2, 1], "counts after the load")
    # Writing the same value again loads again, with EN = 0 too
    await spi_write(dut, COUNT10, 0x34)
    await inc_pulses(dut, 1, en=0)
    await check_digits(dut, [4, 3, 2, 1], "same value again", en=0)


@cocotb.test()
async def test_inc_modes_2_3(dut):
    for mode in (2, 3):
        await start_mode(dut, mode)
        await step(dut, 3)
        await check_digits(dut, [0, 0, 0, 0], f"clk in mode {mode}")
        await inc_pulses(dut, 18)
        await check_digits(dut, [2, 1, 0, 0], f"INC in mode {mode}")
        await inc_pulses(dut, 2, en=0)
        await check_digits(dut, [2, 1, 0, 0], f"EN = 0 in mode {mode}", en=0)


@cocotb.test()
async def test_mode_switch_no_step(dut):
    await start(dut, 1)
    await step(dut, 3)
    assert await lit(dut, 0) == PATTERNS[3], "clk counts"
    # 0 -> 1 with clk low and INC low: no step, and clk no longer counts
    await set_mode(dut, 1)
    assert await lit(dut, 0) == PATTERNS[3]
    await step(dut, 3)
    await check_digits(dut, [3, 0, 0, 0], "mode 1, clk running")
    await inc_pulses(dut, 2)
    await check_digits(dut, [5, 0, 0, 0], "mode 1 counts INC")
    # 1 -> 0 with clk low and INC low: no step, then clk counts, INC does not
    await FallingEdge(dut.clk)
    await set_mode(dut, 0)
    assert await lit(dut, 0) == PATTERNS[5]
    await step(dut, 1)
    await check_digits(dut, [6, 0, 0, 0], "clk counts again")
    await FallingEdge(dut.clk)
    await inc_pulses(dut, 3)
    assert await lit(dut, 0) == PATTERNS[7], "INC ignored again"


@cocotb.test()
async def test_reset_returns_mode0(dut):
    await start_mode(dut, 1)
    await inc_pulses(dut, 3)
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 3)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)
    await check_digits(dut, [0, 0, 0, 0], "after reset")
    await step(dut, 2)
    assert await lit(dut, 0) == PATTERNS[2], "clk counts after reset"
    await FallingEdge(dut.clk)
    await inc_pulses(dut, 4)
    assert await lit(dut, 0) == PATTERNS[3], "INC ignored after reset"


@cocotb.test()
async def test_ctrl_down_and_mode_together(dut):
    await start_mode(dut, 1, ctrl=DOWN)
    await step(dut, 3)
    await check_digits(dut, [0, 0, 0, 0], "clk does not count")
    await inc_pulses(dut, 3)
    await check_digits(dut, [13, 15, 15, 15], "INC counts down")
    # Mode alone in CTRL: counts up again on INC
    await set_mode(dut, 1)
    await FallingEdge(dut.clk)
    await inc_pulses(dut, 2)
    await check_digits(dut, [15, 15, 15, 15], "mode 1 alone counts up")
