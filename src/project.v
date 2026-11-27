/*
 * Copyright (c) 2026 Raman Varabets
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

// Simulation delays are in nanoseconds (the testbench uses the same scale).
// The ASIC flow has no use for the scale, and its linter warns about every
// cell of the library, which has none, so it is left out there.
`ifndef __librelane__
`timescale 1ns / 1ps
`endif

// Three modules below are cells of the gf180 cell library, placed by hand.
// That is for the ASIC flow only. Yosys defines SYNTHESIS in every flow; the
// FPGA build of Tiny Tapeout also defines SYNTH, and has no such cells, so it
// gets the plain logic that simulation uses (and no delays: on an FPGA the
// count modes 1 to 3 and the count load are not timed).
`ifdef SYNTHESIS
`ifndef SYNTH
`define GF180_CELLS
`endif
`endif

// A 2:1 mux that is a real cell of the cell library, so synthesis cannot fold
// it into the logic before it: it stays the last stage in front of a counter
// flip-flop. Without the library (RTL simulation) it is the plain expression.
// The mux2_2 cell is used because the library marks mux2_1 as not to be used.
module count_mux (
    input  wire i0,  // value when s = 0
    input  wire i1,  // value when s = 1
    input  wire s,   // select
    output wire z
);
`ifdef GF180_CELLS
  gf180mcu_fd_sc_mcu7t5v0__mux2_2 u (.I0(i0), .I1(i1), .S(s), .Z(z));
`else
  assign z = s ? i1 : i0;
`endif
endmodule

// A delay line: a chain of delay cells of the library, which the flow keeps
// as they are. In RTL simulation it is a plain delay, and the FPGA build has
// none. It is used twice. On the counter clock it must hold the clock edge
// back until the DEC choice has reached the flip-flops (see project.sdc for
// how the tools check this). In the load pulse it holds the start back until
// the byte to load has settled (see settings).
module delay_line (
    input  wire i,
    output wire z
);
`ifdef GF180_CELLS
  wire [3:0] t;
  gf180mcu_fd_sc_mcu7t5v0__dlyd_2 d0 (.I(i),    .Z(t[0]));
  gf180mcu_fd_sc_mcu7t5v0__dlyd_2 d1 (.I(t[0]), .Z(t[1]));
  gf180mcu_fd_sc_mcu7t5v0__dlyd_2 d2 (.I(t[1]), .Z(t[2]));
  gf180mcu_fd_sc_mcu7t5v0__dlyd_2 d3 (.I(t[2]), .Z(t[3]));
  assign z = t[3];
`else
  assign #10 z = i;
`endif
endmodule

// A delay for EN on its way to the counter: delay cells of the library, kept as they are.
// The counter clock arrives late in the pin modes, so EN must arrive later than it left the pin.
module en_delay (
    input  wire i,
    output wire z
);
`ifdef GF180_CELLS
  wire [1:0] t;
  gf180mcu_fd_sc_mcu7t5v0__dlyd_2 d0 (.I(i),    .Z(t[0]));
  gf180mcu_fd_sc_mcu7t5v0__dlyd_2 d1 (.I(t[0]), .Z(t[1]));
  assign z = t[1];
`else
  assign z = i;
`endif
endmodule

// One digit: a 4-bit counter and its 7 segment pattern. It works out the next
// count for counting up and for counting down all the time; `pick` only
// chooses between the two finished values in front of the flip-flops.
module digit (
    input  wire       clk,    // clock
    input  wire       rst_n,  // reset_n - low to reset
    input  wire       en_up,  // count enable counting up (carry-in of the up chain)
    input  wire       en_dn,  // count enable counting down (borrow-in of the down chain)
    input  wire       en_up_s, // the same as en_up, for the carry shown on CO (not delayed, see en_delay)
    input  wire       en_dn_s, // the same as en_dn, for the borrow shown on CO
    input  wire [3:0] base,   // count base counting up (use 0 for 16)
    input  wire [3:0] base_dn, // count base counting down, the one in effect after the step (same as base unless the digit has a second base)
    input  wire       pick,   // direction that picks the next count: 0 up, 1 down
    input  wire       down,   // direction that the carry-out shows: 0 up, 1 down
    input  wire       load,   // a high pulse sets the counter to `value` at once (asynchronous)
    input  wire [3:0] value,  // the count to load
    output wire [6:0] seg,    // segments, bits are {g,f,e,d,c,b,a}
    output wire       co_up,  // carry-out of the up chain
    output wire       co_dn,  // borrow-out of the down chain
    output wire       co_up_s, // carry-out of the shown up chain (from en_up_s)
    output wire       co_dn_s, // borrow-out of the shown down chain (from en_dn_s)
    output wire       co,     // carry-out of the chain that `down` chooses
    output wire       zero,   // the count is 0
    output wire       at_base, // the count is equal to the base
    output wire       last,   // the count is the last digit of the base
    output wire [3:0] now     // the count
);

  // The 4-bit counter is held in flip-flops, the segments are decoded from it
  wire [3:0] count;

  // The table of segment patterns: one hex digit in, its pattern out
  function [6:0] seg7(input [3:0] hex);
    case (hex)
      //              gfedcba
      4'h0: seg7 = 7'b0111111;
      4'h1: seg7 = 7'b0000110;
      4'h2: seg7 = 7'b1011011;
      4'h3: seg7 = 7'b1001111;
      4'h4: seg7 = 7'b1100110;
      4'h5: seg7 = 7'b1101101;
      4'h6: seg7 = 7'b1111101;
      4'h7: seg7 = 7'b0000111;
      4'h8: seg7 = 7'b1111111;
      4'h9: seg7 = 7'b1101111;
      4'hA: seg7 = 7'b1110111;
      4'hB: seg7 = 7'b1111100;
      4'hC: seg7 = 7'b0111001;
      4'hD: seg7 = 7'b1011110;
      4'hE: seg7 = 7'b1111001;
      4'hF: seg7 = 7'b1110001;
    endcase
  endfunction

  // What the counter will be after the next clock edge, worked out for both
  // directions at once. With the enable at 0 it holds. Counting up it is one
  // more, and the base itself becomes 0. Counting down it is one less, and
  // below 0 it wraps to base - 1 (F when the base is 16). A count at or above
  // the base (a loaded value is taken as is, and the base can be written
  // under the count) is out of range: counting up it runs on to F and wraps
  // to 0, counting down it just counts into range.
  wire [3:0] next_up_raw = count + 4'd1;
  wire [3:0] next_up     = base == next_up_raw ? 4'd0 : next_up_raw;
  wire [3:0] next_down   = zero ? base_dn - 4'd1 : count - 4'd1;
  wire [3:0] count_up    = !en_up ? count : next_up;
  wire [3:0] count_dn    = !en_dn ? count : next_down;

  // The direction is the last choice in front of the flip-flops: one mux cell
  // per bit. `pick` may still be changing when the clock edge is on its way
  // (a DEC press), so the clock is held back (see delay_line).
  wire [3:0] count_next;
  count_mux mux0 (.i0(count_up[0]), .i1(count_dn[0]), .s(pick), .z(count_next[0]));
  count_mux mux1 (.i0(count_up[1]), .i1(count_dn[1]), .s(pick), .z(count_next[1]));
  count_mux mux2 (.i0(count_up[2]), .i1(count_dn[2]), .s(pick), .z(count_next[2]));
  count_mux mux3 (.i0(count_up[3]), .i1(count_dn[3]), .s(pick), .z(count_next[3]));

  // On each rising clock edge the counter takes its new value. Each bit also
  // has an asynchronous set and reset: a load pulse sets the bits that are 1 in
  // `value` and resets the others, at once and with no clock edge. Reset wins
  // over the load. A step while `load` is high is not defined.
  // The FPGA of the Tiny Tapeout FPGA build has no flip-flop with both a set
  // and a reset, so there the bit is two flip-flops with a reset only: the
  // count is p ^ m. The load pulse clears p, and m takes the loaded bit when
  // the pulse ends (while it is high the bit is shown straight from `value`),
  // so after a load the count is `value`. A clock edge writes next ^ m into
  // p, so the count is the next count. Reset clears both.
  genvar i;
  generate
    for (i = 0; i < 4; i = i + 1) begin : bit_ff
`ifdef SYNTH
      wire loading = load & rst_n;
      wire clr = ~rst_n | load;
      reg p, m;
      always @(posedge clk or posedge clr) begin
        if (clr) p <= 1'b0;
        else     p <= count_next[i] ^ m;
      end
      always @(negedge load or negedge rst_n) begin
        if (!rst_n) m <= 1'b0;
        else        m <= value[i];
      end
      assign count[i] = loading ? value[i] : p ^ m;
`else
      wire set = load & value[i] & rst_n;
      wire clr = ~rst_n | (load & ~value[i]);
      reg q;
      always @(posedge clk or posedge set or posedge clr) begin
        if (clr)      q <= 1'b0;
        else if (set) q <= 1'b1;
        else          q <= count_next[i];
      end
      assign count[i] = q;
`endif
    end
  endgenerate

  // The segments are decoded from the count after the flip-flops (one decoder,
  // no segment flip-flops). After reset the count is 0, so the digit 0 shows.
  assign seg = seg7(count);

  // Carry out of each chain, high only when its enable is 1. Counting up it is
  // high on the last digit of the base (F for base 16), so the next digit steps
  // when this one wraps to 0. F is always a last digit: a count out of range
  // wraps there, and that wrap carries too, so no step of the next digit is
  // lost. Counting down it is the borrow: high when the count is 0, so the
  // next digit steps down when this one wraps to base - 1.
  // The same chains are built a second time from the undelayed EN for what CO and the
  // dot show, so that the delay of EN (see en_delay) is not in the path from EN to the outputs.
  assign last  = (next_up_raw == base) | (count == 4'hF);
  assign at_base = (count == base);
  assign co_up = en_up & last;
  assign co_dn = en_dn & zero;
  assign co_up_s = en_up_s & last;
  assign co_dn_s = en_dn_s & zero;
  assign co    = down ? co_dn_s : co_up_s;

  // The count is 0 (used by display mode 1 and by counting down)
  assign zero = count == 4'd0;
  assign now  = count;

endmodule

// The settings: registers written and read over SPI (mode 0, MSB first). A
// write is 16 bits: an address byte, then a data byte. On the 16th rising SCK
// edge the register at that address takes the data. A read is also 16 bits:
// an address byte with bit 7 set, then 8 clocks in which the chip sends the
// byte on MISO (changing on the falling edge, so valid at the 9th to 16th
// rising edges; MOSI is ignored then). The byte is taken at the 8th rising
// edge. MISO is 0 outside the data byte of a read. Several writes and reads
// can follow each other while CS stays low. A write or read cut short by CS
// going high or by reset changes nothing, and so does a write to an address
// without a register. A read changes nothing and an address without a
// register reads 0. Everything here is clocked by SCK, not by clk.
module settings (
    input  wire       sck,    // SPI clock
    input  wire       cs_n,   // SPI chip select, low while a write is sent
    input  wire       mosi,   // SPI data in
    input  wire       rst_n,  // reset_n - low to reset
    input  wire [7:0] live10, // the running count of digits 1 and 0 (digit 1 in bits 7:4)
    input  wire [7:0] live32, // the running count of digits 3 and 2
    output reg        miso,   // SPI data out, driven only while CS is low
    output reg  [7:0] mode,   // display mode of each digit, 2 bits each, digit 0 in bits 1:0
    output reg  [7:0] dot,    // what bit 7 shows for each digit, 2 bits each, digit 0 in bits 1:0
    output reg        down,   // count direction of all digits: 0 up, 1 down
    output reg  [1:0] count_mode,  // what clocks the counter: 0 is clk, 1 to 3 is INC and DEC
    output reg  [7:0] ldata,  // the byte of the last write to COUNT10 or COUNT32 (digit 1 or 3 in bits 7:4)
    output wire       ld10,   // load pulse of digits 1 and 0: high while SCK is high in the last clock of a write to COUNT10
    output wire       ld32,   // load pulse of digits 3 and 2: the same for COUNT32
    output reg  [3:0] base0,  // count base of digit 0 (0 means 16)
    output reg  [3:0] base1,  // count base of digit 1
    output reg  [3:0] base2,  // count base of digit 2
    output reg  [3:0] base3,  // count base of digit 3
    output reg  [3:0] alt2    // base of digit 2 while digit 3 is at its last digit (0: none)
);

  // Register addresses (7 bits, the top bit of the address byte is the read bit)
  localparam [6:0] ADDR_BASE10 = 7'h00;  // {base1, base0}
  localparam [6:0] ADDR_BASE32 = 7'h01;  // {base3, base2}
  localparam [6:0] ADDR_MODE   = 7'h02;  // {mode3, mode2, mode1, mode0}
  localparam [6:0] ADDR_DOT    = 7'h03;  // {dot3, dot2, dot1, dot0}
  localparam [6:0] ADDR_CTRL   = 7'h04;  // bits 1:0 are the count mode, bit 2 is down, 7:3 unused
  localparam [6:0] ADDR_COUNT10 = 7'h05;  // {count1, count0}, loaded at once
  localparam [6:0] ADDR_COUNT32 = 7'h06;  // {count3, count2}, loaded at once
  // 0x08 (second bases of digits 1 and 0) is reserved: writes do nothing, reads 0
  localparam [6:0] ADDR_ALT32  = 7'h09;  // bits 3:0 are alt2, 7:4 reserved (second base of digit 3)

  // The bits received so far in this transfer, newest in bit 0. In a read
  // the byte to send replaces them at the 8th edge and moves up from there.
  reg [14:0] shift;

  // How many bits of this transfer have been received (0..15)
  reg [3:0] bit_count;

  // This transfer is a read (set at the 8th edge, cleared at the 16th)
  reg reading;

  // What ends a transfer at once, wherever it is: CS high, or reset low. With
  // reset in it a transfer can start right after reset even if CS stays low
  // through it (and so is not a new start for the SPI side).
  wire spi_clr = cs_n | ~rst_n;

  // The byte that an address reads: the register, or for the two count
  // addresses the running count of the digits (not the written value)
  function [7:0] read_byte(input [6:0] a);
    case (a)
      ADDR_BASE10:  read_byte = {base1, base0};
      ADDR_BASE32:  read_byte = {base3, base2};
      ADDR_MODE:    read_byte = mode;
      ADDR_DOT:     read_byte = dot;
      ADDR_CTRL:    read_byte = {5'd0, down, count_mode};
      ADDR_COUNT10: read_byte = live10;
      ADDR_COUNT32: read_byte = live32;
      ADDR_ALT32:   read_byte = {4'd0, alt2};
      default:      read_byte = 8'd0;
    endcase
  endfunction

  // At the 8th bit the address is complete: 7 bits are in the shift register
  // and the bit on MOSI is the last one. With the read bit set the byte is
  // taken here. In a write the 16th bit completes the data byte: 15 bits are
  // already in the shift register, and the bit on MOSI is the last one.
  // The counter is held at 0 while CS is high or reset is low, so a cut-short
  // transfer is dropped. It is 4 bits wide, so after the 16th bit it wraps to
  // 0 and the next transfer can follow.
  always @(posedge sck or posedge spi_clr) begin
    if (spi_clr) begin
      bit_count <= 4'd0;
      reading   <= 1'b0;
    end else begin
      bit_count <= bit_count + 4'd1;
      if (bit_count == 4'd7 && shift[6]) begin
        shift   <= {read_byte({shift[5:0], mosi}), 7'd0};
        reading <= 1'b1;
      end else begin
        shift   <= {shift[13:0], mosi};
      end
      if (bit_count == 4'd15) reading <= 1'b0;
    end
  end

  // MISO: the top bit of the byte on the falling edge, so it is stable at the
  // next rising edge. 0 when no byte is being sent.
  always @(negedge sck or posedge spi_clr) begin
    if (spi_clr) miso <= 1'b0;
    else      miso <= reading & shift[14];
  end

  // The complete write: the address (the read bit in front of it is 0 in a
  // write and is not looked at here), then the data byte
  wire [14:0] word = {shift[13:0], mosi};
  wire [6:0]  addr = word[14:8];
  wire [7:0]  data = word[7:0];

  // The register at the address takes the data. To add a register: a new
  // address above, an output port and reset value here, and one case line.
  always @(posedge sck or negedge rst_n) begin
    if (!rst_n) begin
      mode  <= 8'd0;
      dot   <= 8'hAA;  // the carry-out of every digit
      down  <= 1'b0;   // count up
      count_mode <= 2'd0;  // clk counts
      base0 <= 4'd0;
      base1 <= 4'd0;
      base2 <= 4'd0;
      base3 <= 4'd0;
      alt2  <= 4'd0;
    end else if (!cs_n && bit_count == 4'd15 && !reading) begin
      case (addr)
        ADDR_BASE10: {base1, base0} <= data;
        ADDR_BASE32: {base3, base2} <= data;
        ADDR_ALT32:  alt2 <= data[3:0];
        ADDR_MODE:   mode <= data;
        ADDR_DOT:    dot <= data;
        ADDR_CTRL:   begin count_mode <= data[1:0]; down <= data[2]; end
        default: ;  // the counts are loaded below
      endcase
    end
  end

  // Loading a count: the data byte of a write to COUNT10 or COUNT32 is kept
  // on the 16th rising edge (one byte for both registers), and the load pulse
  // is in the high half of that same clock. So the load needs nothing after
  // the 16th rising edge: it is over when SCK falls, whether CS then goes
  // high or stays low, and whatever SCK does next.
  // The pulse is made of flip-flop outputs only, SCK itself is not gated:
  //   go10, go32  rise on the 16th rising edge of a write to that register
  //               and drop on the next rising edge, or at once when CS goes
  //               high or reset is low;
  //   go_late     is go10 | go32 through a delay line, so that the pulse
  //               starts when the byte kept on the same edge has settled;
  //   done        takes go10 | go32 on the falling edge, so it ends the pulse
  //               when SCK falls. It is cleared by reset only, not by CS (it
  //               must not drop before go does), and drops on the first
  //               falling edge of the next transfer, long before the next
  //               load.
  // Each signal changes once on the way up and once on the way down and never
  // two at the same time (but at reset, which overrides the load in the
  // counter anyway), so the pulse cannot glitch. SCK must stay high, and
  // CS low, longer than the delay line takes (see the timing rules in
  // docs/info.md).
  wire writing = !cs_n && bit_count == 4'd15 && !reading;

  always @(posedge sck) begin
    if (writing && (addr == ADDR_COUNT10 || addr == ADDR_COUNT32)) ldata <= data;
  end

  reg go10, go32;
  always @(posedge sck or posedge spi_clr) begin
    if (spi_clr) begin
      go10 <= 1'b0;
      go32 <= 1'b0;
    end else begin
      go10 <= writing && addr == ADDR_COUNT10;
      go32 <= writing && addr == ADDR_COUNT32;
    end
  end

  wire go = go10 | go32;
  wire go_late;
  delay_line load_delay (.i(go), .z(go_late));

  reg done;
  always @(negedge sck or negedge rst_n) begin
    if (!rst_n) done <= 1'b0;
    else        done <= go;
  end

  assign ld10 = go10 & go_late & ~done;
  assign ld32 = go32 & go_late & ~done;

endmodule

module tt_um_cyberhuman_7segment (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered, so you can ignore it
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);

  // EN is the count enable, it comes from input pin 3
  wire en = ui_in[3];
  wire en_cnt;  // EN as the counter sees it
  en_delay en_pad (.i(en), .z(en_cnt));

  // SEL picks which digit is shown in the count modes 0 and 1: 0 = lowest
  // digit, 3 = highest digit. It comes from bidirectional pins uio[4] (SEL0)
  // and uio[5] (SEL1), used as inputs there. In the modes 2 and 3 the chip
  // picks the digit itself (see the scan counter below).
  wire [1:0] sel_pin = uio_in[5:4];

  // SPI pins: ui[0] is CS (active low), ui[1] is MOSI, ui[2] is SCK.
  // uio[2] is MISO, driven while CS is low.
  wire cs_n = ui_in[0];
  wire mosi = ui_in[1];
  wire sck  = ui_in[2];

  // Display mode, decimal point and counter base of each digit, and the
  // count direction, set over SPI (after reset every digit is shown as is,
  // the decimal point is the carry-out, all bases are 16 and it counts up)
  wire [7:0] mode;
  wire [7:0] dot;
  wire       down;
  wire [1:0] count_mode;
  wire [3:0] base0, base1, base2, base3, alt2;
  wire [7:0] ldata;
  wire [7:0] live10, live32;
  wire       miso;
  wire       ld10, ld32;
  settings settings0 (.sck, .cs_n, .mosi, .rst_n, .live10, .live32, .miso, .mode, .dot, .down, .count_mode, .ldata,
                      .ld10, .ld32, .base0, .base1, .base2, .base3, .alt2);

  // INC counts up and DEC counts down in the modes 1 to 3. They come from
  // input pins 4 and 5. A step happens when the input is pressed.
  // Why it works: the counter has one clock, a delayed copy of INC or DEC,
  // so its rising edge is the press. The digits have both next counts ready;
  // the DEC pin itself picks one in front of the flip-flops, and the clock
  // edge arrives later than that choice (the delay line, checked by STA).
  // While DEC is low the up count waits, so an INC press needs no switch.
  wire inc = ui_in[4];
  wire dec = ui_in[5];

  // The direction flip-flop: the rising edge of DEC sets it (D is constant 1),
  // INC high clears it (INC wins if both are high), and so does reset (an OR
  // of the two on the one asynchronous clear). It is for the display only:
  // the carry-out shown in the modes 1 to 3 follows the last direction pressed.
  wire dec_clr = inc | ~rst_n;
  reg  dec_dir;
  always @(posedge dec or posedge dec_clr) begin
    if (dec_clr) dec_dir <= 1'b0;
    else         dec_dir <= 1'b1;
  end

  // The counter clock: clk in mode 0, in the other modes a delayed copy of
  // INC or DEC (low while both are low). This is a plain switch, not
  // glitch-free: a write to the mode makes an edge on it if clk is high.
  wire pin_clk;
  delay_line pin_delay (.i(inc | dec), .z(pin_clk));
  wire count_clk = (count_mode == 2'd0) ? clk : pin_clk;

  // The direction that picks the next count: CTRL bit 2 in mode 0, the DEC pin
  // itself in the other modes (a mux cell, so the choice is as short as it can be)
  wire pick_down;
  count_mux pick_mux (.i0(dec), .i1(down), .s(count_mode == 2'd0), .z(pick_down));

  // The direction that the carry-out shows: CTRL bit 2 in mode 0, the last
  // direction pressed in the other modes
  wire count_down = (count_mode == 2'd0) ? down : dec_dir;

  // Loading a count: a write to COUNT10 or COUNT32 makes a pulse on ld10 or
  // ld32 (see settings) that sets the counter flip-flops of its two digits
  // through their asynchronous set and reset, with no clock edge, whatever the
  // count mode and EN. The next step counts from the loaded value.

  // Segments and carry-out of each of the four digits
  wire [6:0] seg0, seg1, seg2, seg3;
  wire       co0, co1, co2, co3;
  wire       cu0, cu1, cu2, cu3;  // carry-out, up chain
  wire       cd0, cd1, cd2, cd3;  // borrow-out, down chain
  wire       su0, su1, su2, su3;  // the same chains from the undelayed EN (shown on CO)
  wire       sd0, sd1, sd2, sd3;
  wire       zero0, zero1, zero2, zero3;
  wire       atb0, atb1, atb2, atb3;
  wire       last0, last1, last2, last3;

  // The second base of digit 2: while digit 3 is at the last digit of its base,
  // digit 2 uses alt2 as its base (0 means no second base). Counting up that is
  // judged on the count of digit 3 now. Counting down a wrap of digit 2 comes
  // with a step of digit 3 on the same edge, so it is judged on digit 3 after
  // the step: it is at the last digit then if it is 0 (it wraps to the last
  // digit) or at its base (it steps to the last digit).
  wire       alt2_on     = alt2 != 4'd0;
  wire       last3_after = zero3 | atb3;
  wire [3:0] base2_up    = (alt2_on & last3)       ? alt2 : base2;
  wire [3:0] base2_dn    = (alt2_on & last3_after) ? alt2 : base2;

  // Four digits in two chains, each with its own base (16 after reset, so
  // together a 16-bit counter 0000..FFFF; bases 10, 6, 10, 6 make a clock
  // 00:00..59:59). The lowest digit counts when EN is 1, each next digit
  // counts when the digit before it has a carry-out. The up chain (carry) and
  // the down chain (borrow) are both worked out all the time; each digit
  // picks its next count from them by the direction, as the last step.
  digit digit0 (.clk(count_clk), .rst_n, .en_up(en_cnt),  .en_dn(en_cnt),  .en_up_s(en), .en_dn_s(en), .base(base0), .base_dn(base0), .pick(pick_down), .down(count_down), .load(ld10), .value(ldata[3:0]), .seg(seg0), .co_up(cu0), .co_dn(cd0), .co_up_s(su0), .co_dn_s(sd0), .co(co0), .zero(zero0), .at_base(atb0), .last(last0), .now(live10[3:0]));
  digit digit1 (.clk(count_clk), .rst_n, .en_up(cu0), .en_dn(cd0), .en_up_s(su0), .en_dn_s(sd0), .base(base1), .base_dn(base1), .pick(pick_down), .down(count_down), .load(ld10), .value(ldata[7:4]), .seg(seg1), .co_up(cu1), .co_dn(cd1), .co_up_s(su1), .co_dn_s(sd1), .co(co1), .zero(zero1), .at_base(atb1), .last(last1), .now(live10[7:4]));
  digit digit2 (.clk(count_clk), .rst_n, .en_up(cu1), .en_dn(cd1), .en_up_s(su1), .en_dn_s(sd1), .base(base2_up), .base_dn(base2_dn), .pick(pick_down), .down(count_down), .load(ld32), .value(ldata[3:0]), .seg(seg2), .co_up(cu2), .co_dn(cd2), .co_up_s(su2), .co_dn_s(sd2), .co(co2), .zero(zero2), .at_base(atb2), .last(last2), .now(live32[3:0]));
  digit digit3 (.clk(count_clk), .rst_n, .en_up(cu2), .en_dn(cd2), .en_up_s(su2), .en_dn_s(sd2), .base(base3), .base_dn(base3), .pick(pick_down), .down(count_down), .load(ld32), .value(ldata[7:4]), .seg(seg3), .co_up(cu3), .co_dn(cd3), .co_up_s(su3), .co_dn_s(sd3), .co(co3), .zero(zero3), .at_base(atb3), .last(last3), .now(live32[7:4]));

  // What each digit shows, by its 2-bit display mode (the segments only, CO
  // is not affected): 0 = the digit as is, 1 = the digit unless its own
  // count is 0, 2 = nothing, 3 = a minus (segment G only).
  function [6:0] apply_mode(input [1:0] m, input [6:0] seg, input zero);
    case (m)
      2'd0: apply_mode = seg;
      2'd1: apply_mode = zero ? 7'd0 : seg;
      2'd2: apply_mode = 7'd0;
      2'd3: apply_mode = 7'b1000000;
    endcase
  endfunction

  // What bit 7 (the decimal point) shows, by the 2-bit dot value of a digit:
  // 0 = off, 1 = on, 2 = the carry-out of the digit, 3 = its inverse.
  localparam [1:0] DOT_OFF = 2'd0;
  localparam [1:0] DOT_ON  = 2'd1;
  localparam [1:0] DOT_CO  = 2'd2;
  localparam [1:0] DOT_NCO = 2'd3;

  function apply_dot(input [1:0] d, input co);
    case (d)
      DOT_OFF: apply_dot = 1'b0;
      DOT_ON:  apply_dot = 1'b1;
      DOT_CO:  apply_dot = co;
      DOT_NCO: apply_dot = ~co;
    endcase
  endfunction

  // The scan counter: in the modes 2 and 3 it steps 0, 1, 2, 3, 0 on every
  // rising edge of clk (not of the counter clock), whatever EN is. In the
  // modes 0 and 1 it holds. Reset clears it. The mode comes from the SCK side
  // without a synchroniser, like the other settings.
  reg [1:0] scan;
  wire      scanning = count_mode[1];
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n)        scan <= 2'd0;
    else if (scanning) scan <= scan + 2'd1;
  end

  // The digit shown: the SEL pins in the modes 0 and 1, the scan counter in
  // the modes 2 and 3
  wire [1:0] sel = scanning ? scan : sel_pin;

  // The selector: SEL chooses which digit's {dot, seg} goes to the output pins.
  // It is plain logic after the flip-flops, so a switch change shows at once,
  // without a clock edge. The dot is the top bit, the segments are the lower
  // seven. The carry chain between the digits uses the real carry-out.
  reg [7:0] shown;
  always @(*) begin
    case (sel)
      2'd0: shown = {apply_dot(dot[1:0], co0), apply_mode(mode[1:0], seg0, zero0)};
      2'd1: shown = {apply_dot(dot[3:2], co1), apply_mode(mode[3:2], seg1, zero1)};
      2'd2: shown = {apply_dot(dot[5:4], co2), apply_mode(mode[5:4], seg2, zero2)};
      2'd3: shown = {apply_dot(dot[7:6], co3), apply_mode(mode[7:6], seg3, zero3)};
    endcase
  end

  assign uo_out  = shown;

  // The digit select goes out on the bidirectional pins. Mode 2: the scan
  // number on uio[5:4]. Mode 3: one active-high line per digit on uio[7:4]
  // (uio[4] is digit 0). In the modes 0 and 1 nothing is driven there.
  // uio[1] is CARRY and uio[0] is BORROW in every count mode: the carry-out
  // and the borrow-out of the whole counter, taken from the chains of the
  // undelayed EN (the ones that CO and the dot show). uio[2] is
  // MISO, an output only while CS is low, and uio[3] is unused.
  wire mode2 = count_mode == 2'd2;
  wire mode3 = count_mode == 2'd3;
  wire [3:0] one_hot = 4'b0001 << scan;
  wire carry  = su3;
  wire borrow = sd3;
  assign uio_out = {mode3 ? {one_hot, 4'b0000} : mode2 ? {2'b00, scan, 4'b0000} : 8'h00} | {5'b0, miso, carry, borrow};
  assign uio_oe  = (mode3 ? 8'hF3 : mode2 ? 8'h33 : 8'h03) | {5'b0, ~cs_n, 2'b0};

  // List all unused inputs to prevent warnings, and the outputs of the digits
  // that nothing uses: the carries out of the delayed chains of digit 3, and
  // `at_base` and `last` of the digits other than digit 3
  wire _unused = &{ena, uio_in[7:6], uio_in[3:0], ui_in[7:6],
                   cu3, cd3, atb0, atb1, atb2, last0, last1, last2, 1'b0};

endmodule
