/*
 * Copyright (c) 2026 Raman Varabets
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

// One digit: a 4-bit counter and its 7 segment pattern
module digit (
    input  wire       clk,    // clock
    input  wire       rst_n,  // reset_n - low to reset
    input  wire       en,     // count enable (carry-in)
    input  wire [3:0] base,   // count base (use 0 for 16)
    input  wire       down,   // direction: 0 counts up, 1 counts down
    output reg  [6:0] seg,    // segments, bits are {g,f,e,d,c,b,a}
    output wire       co,     // carry-out
    output wire       zero    // the count is 0
);

  // The 4-bit counter and the 7 segment outputs are both held in flip-flops
  reg [3:0] count;

  // The table of segment patterns: one hex digit in, its pattern out
  function [6:0] seg7(input [3:0] value);
    case (value)
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

  // The pattern shown after reset: the digit 0, taken from the table
  localparam [6:0] SEG_RESET = seg7(4'h0);

  // What the counter will be after the next clock edge. With EN = 0 it holds.
  // Counting up it is one more, and the base itself becomes 0. Counting down
  // it is one less, and below 0 it wraps to base - 1 (F when the base is 16).
  // A count above the base just counts down into range.
  wire [3:0] next_up_raw = count + 4'd1;
  wire [3:0] next_up     = base == next_up_raw ? 4'd0 : next_up_raw;
  wire [3:0] next_down   = zero ? base - 4'd1 : count - 4'd1;

  wire [3:0] next_count = !en ? count : down ? next_down : next_up;

  // Segment pattern for that next digit (plain logic, no flip-flops)
  wire [6:0] next_seg = seg7(next_count);

  // On each rising clock edge the counter and the segments take their new
  // values together, so the segment pins are driven straight from flip-flops
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      count <= 4'd0;
      seg   <= SEG_RESET;
    end else begin
      count <= next_count;
      seg   <= next_seg;
    end
  end

  // Carry out, high only when EN is 1. Counting up it is high on the last
  // digit of the base (F for base 16), so the next digit steps when this one
  // wraps to 0. Counting down it is the borrow: high when the count is 0,
  // so the next digit steps down when this one wraps to base - 1.
  assign co = en & (down ? zero : count + 4'd1 == base);

  // The count is 0 (used by display mode 1 and by counting down)
  assign zero = count == 4'd0;

endmodule

// The settings: registers written over SPI (mode 0, MSB first). A write is 16
// bits: an address byte, then a data byte. On the 16th rising SCK edge the
// register at that address takes the data. Several writes can follow each
// other while CS stays low. A write cut short by CS going high changes
// nothing. Bit 7 of the address is reserved for reads: a write with it set
// changes nothing, and so does an address without a register.
// Everything here is clocked by SCK, not by clk.
module settings (
    input  wire       sck,    // SPI clock
    input  wire       cs_n,   // SPI chip select, low while a write is sent
    input  wire       mosi,   // SPI data in
    input  wire       rst_n,  // reset_n - low to reset
    output reg  [7:0] mode,   // display mode of each digit, 2 bits each, digit 0 in bits 1:0
    output reg  [7:0] dot,    // what bit 7 shows for each digit, 2 bits each, digit 0 in bits 1:0
    output reg        down,   // count direction of all digits: 0 up, 1 down
    output reg  [3:0] base0,  // count base of digit 0 (0 means 16)
    output reg  [3:0] base1,  // count base of digit 1
    output reg  [3:0] base2,  // count base of digit 2
    output reg  [3:0] base3   // count base of digit 3
);

  // Register addresses (7 bits, the top bit of the address byte is the read bit)
  localparam [6:0] ADDR_BASE10 = 7'h00;  // {base1, base0}
  localparam [6:0] ADDR_BASE32 = 7'h01;  // {base3, base2}
  localparam [6:0] ADDR_MODE   = 7'h02;  // {mode3, mode2, mode1, mode0}
  localparam [6:0] ADDR_DOT    = 7'h03;  // {dot3, dot2, dot1, dot0}
  localparam [6:0] ADDR_CTRL   = 7'h04;  // bit 2 is down; bits 1:0 are reserved, 7:3 unused

  // The bits received so far in this write, newest in bit 0
  reg [14:0] shift;

  // How many bits of this write have been received (0..15)
  reg [3:0] bit_count;

  // The write is complete when the 16th bit arrives: 15 bits are already in
  // the shift register, and the bit on MOSI is the last one.
  // The counter is held at 0 while CS is high, so a cut-short write is dropped.
  // It is 4 bits wide, so after the 16th bit it wraps to 0 and the next
  // write can follow.
  always @(posedge sck or posedge cs_n) begin
    if (cs_n) begin
      bit_count <= 4'd0;
    end else begin
      bit_count <= bit_count + 4'd1;
      shift     <= {shift[13:0], mosi};
    end
  end

  // The complete write: the address byte, then the data byte
  wire [15:0] word = {shift, mosi};
  wire        read_bit = word[15];
  wire [6:0]  addr = word[14:8];
  wire [7:0]  data = word[7:0];

  // The register at the address takes the data. To add a register: a new
  // address above, an output port and reset value here, and one case line.
  always @(posedge sck or negedge rst_n) begin
    if (!rst_n) begin
      mode  <= 8'd0;
      dot   <= 8'hAA;  // the carry-out of every digit
      down  <= 1'b0;   // count up
      base0 <= 4'd0;
      base1 <= 4'd0;
      base2 <= 4'd0;
      base3 <= 4'd0;
    end else if (!cs_n && bit_count == 4'd15 && !read_bit) begin
      case (addr)
        ADDR_BASE10: {base1, base0} <= data;
        ADDR_BASE32: {base3, base2} <= data;
        ADDR_MODE:   mode <= data;
        ADDR_DOT:    dot <= data;
        ADDR_CTRL:   down <= data[2];
        default: ;
      endcase
    end
  end

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

  // EN is the count enable, it comes from input pin 0
  wire en = ui_in[0];

  // SEL picks which digit is shown: 0 = lowest digit, 3 = highest digit
  wire [1:0] sel = ui_in[2:1];

  // SPI pins: uio[0] is CS (active low), uio[1] is MOSI, uio[3] is SCK.
  // uio[2] is kept for MISO, it is not driven.
  wire cs_n = uio_in[0];
  wire mosi = uio_in[1];
  wire sck  = uio_in[3];

  // Display mode, decimal point and counter base of each digit, and the
  // count direction, set over SPI (after reset every digit is shown as is,
  // the decimal point is the carry-out, all bases are 16 and it counts up)
  wire [7:0] mode;
  wire [7:0] dot;
  wire       down;
  wire [3:0] base0, base1, base2, base3;
  settings settings0 (.sck, .cs_n, .mosi, .rst_n, .mode, .dot, .down, .base0, .base1, .base2, .base3);

  // Segments and carry-out of each of the four digits
  wire [6:0] seg0, seg1, seg2, seg3;
  wire       co0, co1, co2, co3;
  wire       zero0, zero1, zero2, zero3;

  // Four digits in a chain, each with its own base (16 after reset, so
  // together a 16-bit counter 0000..FFFF; bases 10, 6, 10, 6 make a clock
  // 00:00..59:59). The lowest digit counts when EN is 1, each next digit
  // counts when the digit before it has a carry-out (counting down, a borrow).
  digit digit0 (.clk, .rst_n, .en,      .base(base0), .down, .seg(seg0), .co(co0), .zero(zero0));
  digit digit1 (.clk, .rst_n, .en(co0), .base(base1), .down, .seg(seg1), .co(co1), .zero(zero1));
  digit digit2 (.clk, .rst_n, .en(co1), .base(base2), .down, .seg(seg2), .co(co2), .zero(zero2));
  digit digit3 (.clk, .rst_n, .en(co2), .base(base3), .down, .seg(seg3), .co(co3), .zero(zero3));

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
  assign uio_out = 0;
  assign uio_oe  = 0;

  // List all unused inputs to prevent warnings
  wire _unused = &{ena, uio_in[7:4], uio_in[2], ui_in[7:3], 1'b0};

endmodule
