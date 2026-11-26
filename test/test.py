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


def frame(*bases, pad=0):
    # The 24-bit frame for the given bases and pad bits (bit n is digit n).
    # One base is used for all four digits, four bases are given for digits
    # 0..3 (digit 3 goes first). The 4 top bits are unused and sent as 0.
    if len(bases) == 1:
        bases = bases * 4
    assert len(bases) == 4
    return ((pad & 0xF) << 16) | sum(
        (b & 0xF) << (4 * d) for d, b in enumerate(bases))


async def spi_write(dut, value, bits=24):
    # Bit-bang one SPI frame, mode 0, MSB first, CS idle high. MOSI changes
    # while SCK is low and is sampled on the rising edge. Fewer bits than 24
    # make a cut-short frame (the first bits of the value are sent). The whole
    # write takes 5 us, well inside half a clock cycle (5 us), so it fits
    # between clock edges.
    dut.uio_in.value = 0            # CS low, SCK low
    await Timer(SPI_HALF, unit="ns")
    for i in range(bits):
        bit = (value >> (23 - i)) & 1
        dut.uio_in.value = bit * MOSI
        await Timer(SPI_HALF, unit="ns")
        dut.uio_in.value = bit * MOSI | SCK
        await Timer(SPI_HALF, unit="ns")
        dut.uio_in.value = bit * MOSI
    await Timer(SPI_HALF, unit="ns")
    dut.uio_in.value = CS           # CS back high
    await Timer(SPI_HALF, unit="ns")


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
    # Reset clears the bases, so they are written after reset. EN is held at 0
    # during the write and one clock cycle, so the count stays at 0.
    if base is not None or pad:
        base = 0 if base is None else base
        bases = base if isinstance(base, (list, tuple)) else [base]
        dut.ui_in.value = ui(0, sel)
        await spi_write(dut, frame(*bases, pad=pad))
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


@cocotb.test()
async def test_spi_short_frame_ignored(dut):
    await start(dut, 1, base=10)
    await spi_write(dut, frame(3), bits=23)   # cut short
    await spi_write(dut, frame(0), bits=3)
    assert await read_base(dut) == 9


@cocotb.test()
async def test_spi_cs_high_ignored(dut):
    await start(dut, 1, base=10)
    # SCK edges with CS high: 24 clocks carrying 1s, nothing happens
    for _ in range(24):
        dut.uio_in.value = CS | MOSI | SCK
        await Timer(SPI_HALF, unit="ns")
        dut.uio_in.value = CS | MOSI
        await Timer(SPI_HALF, unit="ns")
    assert await read_base(dut) == 9


@cocotb.test()
async def test_spi_two_frames_second_wins(dut):
    await start(dut, 1)
    # Two frames in one CS-low period: 48 SCK edges, the second frame wins
    dut.uio_in.value = 0
    await Timer(SPI_HALF, unit="ns")
    for value in (frame(0xA), frame(3)):
        for i in range(24):
            bit = (value >> (23 - i)) & 1
            dut.uio_in.value = bit * MOSI
            await Timer(SPI_HALF, unit="ns")
            dut.uio_in.value = bit * MOSI | SCK
            await Timer(SPI_HALF, unit="ns")
            dut.uio_in.value = bit * MOSI
    dut.uio_in.value = CS
    await Timer(SPI_HALF, unit="ns")
    assert await read_base(dut) == 2


@cocotb.test()
async def test_spi_half_frame_ignored(dut):
    await start(dut, 1, base=[10, 6, 4, 3])
    # 8 bits of a frame, CS high, then a full frame: only the full one counts
    await spi_write(dut, frame(2), bits=8)
    n = 0
    for _ in range(61):
        values = await read_digits(dut)
        expected = [n % 10, n // 10 % 6, n // 60 % 4, n // 240 % 3]
        assert values == [PATTERNS[e] for e in expected], f"count {n}"
        dut.ui_in.value = ui(1, 0)
        await FallingEdge(dut.clk)
        n += 1


@cocotb.test()
async def test_frame_order(dut):
    # The frame 0x5432 is digit 3 = 5, digit 2 = 4, digit 1 = 3, digit 0 = 2.
    # Each digit shows its base - 1 just before it wraps: check via the carry.
    cocotb.start_soon(Clock(dut.clk, 10, unit="us").start())
    dut.ena.value = 1
    dut.ui_in.value = ui(0, 0)
    dut.uio_in.value = CS
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)
    await spi_write(dut, 0x5432)
    await FallingEdge(dut.clk)
    n = 0
    for _ in range(2 * 3 * 4 * 5 + 3):
        values = await read_digits(dut, en=1)
        expected = [n % 2, n // 2 % 3, n // 6 % 4, n // 24 % 5]
        assert values == [PATTERNS[e] for e in expected], f"count {n}"
        dut.ui_in.value = ui(1, 0)
        await FallingEdge(dut.clk)
        n += 1


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


@cocotb.test()
async def test_reset_returns_base_16(dut):
    await start(dut, 1, base=10)
    assert await read_base(dut) == 9
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 3)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)
    assert await read_base(dut) == 15


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
async def test_spi_16_bit_frame_ignored(dut):
    await start(dut, 1, base=10, pad=0b1110)
    # A 16-bit frame is cut short now: the pad bits and bases stay
    await spi_write(dut, frame(3), bits=16)
    assert await read_digits(dut) == [PATTERNS[0], 0, 0, 0]
    assert await read_base(dut) == 9


@cocotb.test()
async def test_reset_clears_pad(dut):
    await start(dut, 1, base=10, pad=0b1111)
    assert await read_digits(dut) == [0, 0, 0, 0]
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 3)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)
    assert await read_digits(dut) == [PATTERNS[0]] * 4
