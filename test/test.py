# SPDX-FileCopyrightText: © 2026 Raman Varabets
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge

# Segment patterns {g,f,e,d,c,b,a} for the digits 0..F
PATTERNS = [0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07,
            0x7F, 0x6F, 0x77, 0x7C, 0x39, 0x5E, 0x79, 0x71]


async def start(dut, en):
    # Start the clock, hold reset for a few cycles, then release it
    cocotb.start_soon(Clock(dut.clk, 10, unit="us").start())
    dut.ena.value = 1
    dut.ui_in.value = en
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    # Look at the outputs on the falling edge, away from the rising edge
    await FallingEdge(dut.clk)


@cocotb.test()
async def test_reset(dut):
    await start(dut, 1)
    # Reset shows digit 0 and CO is low
    assert dut.uo_out.value == PATTERNS[0]


@cocotb.test()
async def test_count_and_carry(dut):
    await start(dut, 1)
    # Two full rounds: every digit in order, then wrap to 0
    for i in range(32):
        digit = i % 16
        assert dut.uo_out.value == (PATTERNS[digit] | (0x80 if digit == 15 else 0)), f"step {i}"
        await FallingEdge(dut.clk)


@cocotb.test()
async def test_hold(dut):
    await start(dut, 1)
    # Count to each digit, then stop with EN = 0: value holds and CO is 0
    for digit in range(16):
        assert dut.uo_out.value == (PATTERNS[digit] | (0x80 if digit == 15 else 0))
        dut.ui_in.value = 0
        await FallingEdge(dut.clk)
        for _ in range(4):
            assert dut.uo_out.value == PATTERNS[digit], f"hold at {digit}"
            await FallingEdge(dut.clk)
        dut.ui_in.value = 1
        await FallingEdge(dut.clk)
