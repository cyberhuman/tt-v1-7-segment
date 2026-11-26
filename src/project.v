/*
 * Copyright (c) 2026 Raman Varabets
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

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

  // The 4-bit counter and the 7 segment outputs are both held in flip-flops
  reg [3:0] count;
  reg [6:0] seg;  // bits are {g,f,e,d,c,b,a}

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
  wire co = en & (count == 4'hF);

  // CO is the top output bit, the segments are the lower seven
  assign uo_out  = {co, seg};
  assign uio_out = 0;
  assign uio_oe  = 0;

  // List all unused inputs to prevent warnings
  wire _unused = &{ena, uio_in, ui_in[7:1], 1'b0};

endmodule
