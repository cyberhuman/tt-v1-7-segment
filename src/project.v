/*
 * Copyright (c) 2026 Raman Varabets
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

// One hex digit: a 4-bit counter and its 7 segment pattern
module hex_digit (
    input  wire       clk,    // clock
    input  wire       rst_n,  // reset_n - low to reset
    input  wire       en,     // count enable (carry-in)
    output reg  [6:0] seg,    // segments, bits are {g,f,e,d,c,b,a}
    output wire       co      // carry-out
);

  // The 4-bit counter and the 7 segment outputs are both held in flip-flops
  reg [3:0] count;

  // The table of segment patterns: one hex digit in, its pattern out
  function [6:0] seg7(input [3:0] digit);
    case (digit)
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

  // What the counter will be after the next clock edge: one more when EN is 1
  wire [3:0] next_count = en ? count + 4'd1 : count;

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

  // Carry out: high when EN is 1 and the digit is F
  assign co = en & (count == 4'hF);

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

  // Segments and carry-out of each of the four digits
  wire [6:0] seg0, seg1, seg2, seg3;
  wire       co0, co1, co2, co3;

  // Four digits in a chain: together a 16-bit counter 0000..FFFF.
  // The lowest digit counts when EN is 1, each next digit counts when the
  // digit before it has a carry-out.
  hex_digit digit0 (.clk(clk), .rst_n(rst_n), .en(en),  .seg(seg0), .co(co0));
  hex_digit digit1 (.clk(clk), .rst_n(rst_n), .en(co0), .seg(seg1), .co(co1));
  hex_digit digit2 (.clk(clk), .rst_n(rst_n), .en(co1), .seg(seg2), .co(co2));
  hex_digit digit3 (.clk(clk), .rst_n(rst_n), .en(co2), .seg(seg3), .co(co3));

  // The selector: SEL chooses which digit's {co, seg} goes to the output pins.
  // It is plain logic after the flip-flops, so a switch change shows at once,
  // without a clock edge. CO is the top bit, the segments are the lower seven.
  reg [7:0] shown;
  always @(*) begin
    case (sel)
      2'd0: shown = {co0, seg0};
      2'd1: shown = {co1, seg1};
      2'd2: shown = {co2, seg2};
      2'd3: shown = {co3, seg3};
    endcase
  end

  assign uo_out  = shown;
  assign uio_out = 0;
  assign uio_oe  = 0;

  // List all unused inputs to prevent warnings
  wire _unused = &{ena, uio_in, ui_in[7:3], 1'b0};

endmodule
