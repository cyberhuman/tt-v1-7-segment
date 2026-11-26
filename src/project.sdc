# Based on LibreLane's default base.sdc (kept for clk), plus the SPI clock sck and the counter clocks inc and dec
# CLOCK_PORT lists four ports (clk, the SPI clock, INC and DEC); clk is the first one
set clock_port [lindex $::env(CLOCK_PORT) 0]
set port_args [get_ports $clock_port]
puts "\[INFO] Using clock $clock_port…"
create_clock {*}$port_args -name $clock_port -period $::env(CLOCK_PERIOD)

# The SPI clock SCK is on uio_in[3]. It is a second clock, 100 ns period,
# and is asynchronous to clk: no paths between the two are timed.
set sck_port [get_ports {uio_in[3]}]
create_clock $sck_port -name sck -period 100

# The counter clock INC is on ui_in[1]. It is a third clock, 200 ns period,
# asynchronous to clk and sck. It clocks the counter in the count modes 1 to 3.
# The period stands for the shortest INC or DEC pulse, and the shortest gap
# between pulses, that the checks assume: 100 ns each.
set inc_port [get_ports {ui_in[1]}]
create_clock $inc_port -name inc -period 200

# The counter clock DEC is on ui_in[2]: a fourth clock, 200 ns period, asynchronous
# to the others, treated like inc. It sets the direction flip-flop. The paths from that
# flip-flop to the counter are between unrelated clocks by this definition; they are
# separated by the pulse width of INC and DEC, not by STA.
set dec_port [get_ports {ui_in[2]}]
create_clock $dec_port -name dec -period 200

set_clock_groups -asynchronous -group [get_clocks $clock_port] -group [get_clocks sck] -group [get_clocks inc] -group [get_clocks dec]

set input_delay_value [expr $::env(CLOCK_PERIOD) * $::env(IO_DELAY_CONSTRAINT) / 100]
set output_delay_value [expr $::env(CLOCK_PERIOD) * $::env(IO_DELAY_CONSTRAINT) / 100]
puts "\[INFO] Setting output delay to: $output_delay_value"
puts "\[INFO] Setting input delay to: $input_delay_value"

set_max_fanout $::env(MAX_FANOUT_CONSTRAINT) [current_design]
if { [info exists ::env(MAX_TRANSITION_CONSTRAINT)] } {
    set_max_transition $::env(MAX_TRANSITION_CONSTRAINT) [current_design]
}
if { [info exists ::env(MAX_CAPACITANCE_CONSTRAINT)] } {
    set_max_capacitance $::env(MAX_CAPACITANCE_CONSTRAINT) [current_design]
} 

set clk_input [get_port $clock_port]
set clk_indx [lsearch [all_inputs] $clk_input]
set all_inputs_wo_clk [lreplace [all_inputs] $clk_indx $clk_indx ""]
set sck_indx [lsearch $all_inputs_wo_clk $sck_port]
set all_inputs_wo_clk [lreplace $all_inputs_wo_clk $sck_indx $sck_indx ""]
set inc_indx [lsearch $all_inputs_wo_clk $inc_port]
set all_inputs_wo_clk [lreplace $all_inputs_wo_clk $inc_indx $inc_indx ""]
set dec_indx [lsearch $all_inputs_wo_clk $dec_port]
set all_inputs_wo_clk [lreplace $all_inputs_wo_clk $dec_indx $dec_indx ""]

#set rst_input [get_port resetn]
#set rst_indx [lsearch [all_inputs] $rst_input]
#set all_inputs_wo_clk_rst [lreplace $all_inputs_wo_clk $rst_indx $rst_indx ""]
set all_inputs_wo_clk_rst $all_inputs_wo_clk

# correct resetn
set clocks [get_clocks $clock_port]
set all_clocks [get_clocks *]

set_input_delay $input_delay_value -clock $clocks $all_inputs_wo_clk_rst
set_output_delay $output_delay_value -clock $clocks [all_outputs]

# CS and MOSI arrive with SCK, so they are timed against sck (same 20% rule)
set sck_delay_value [expr 100 * $::env(IO_DELAY_CONSTRAINT) / 100]
set_input_delay $sck_delay_value -clock [get_clocks sck] [get_ports {uio_in[0] uio_in[1]}]

# The counter is clocked when INC or DEC falls, so the delays against inc and dec
# are referenced to the falling edge (-clock_fall).
# EN also gates the counter when INC clocks it, so it is timed against inc too,
# and so are the outputs, which are launched by the counter flip-flops
set inc_delay_value [expr 100 * $::env(IO_DELAY_CONSTRAINT) / 100]
set_input_delay $inc_delay_value -clock_fall -clock [get_clocks inc] -add_delay [get_ports {ui_in[0]}]
set_output_delay $inc_delay_value -clock_fall -clock [get_clocks inc] -add_delay [all_outputs]
set_input_delay $inc_delay_value -clock_fall -clock [get_clocks dec] -add_delay [get_ports {ui_in[0]}]
set_output_delay $inc_delay_value -clock_fall -clock [get_clocks dec] -add_delay [all_outputs]

if { ![info exists ::env(SYNTH_CLK_DRIVING_CELL)] } {
    set ::env(SYNTH_CLK_DRIVING_CELL) $::env(SYNTH_DRIVING_CELL)
}

set_driving_cell \
    -lib_cell [lindex [split $::env(SYNTH_DRIVING_CELL) "/"] 0] \
    -pin [lindex [split $::env(SYNTH_DRIVING_CELL) "/"] 1] \
    $all_inputs_wo_clk_rst

set_driving_cell \
    -lib_cell [lindex [split $::env(SYNTH_CLK_DRIVING_CELL) "/"] 0] \
    -pin [lindex [split $::env(SYNTH_CLK_DRIVING_CELL) "/"] 1] \
    $clk_input

set_driving_cell \
    -lib_cell [lindex [split $::env(SYNTH_CLK_DRIVING_CELL) "/"] 0] \
    -pin [lindex [split $::env(SYNTH_CLK_DRIVING_CELL) "/"] 1] \
    $sck_port

set_driving_cell \
    -lib_cell [lindex [split $::env(SYNTH_CLK_DRIVING_CELL) "/"] 0] \
    -pin [lindex [split $::env(SYNTH_CLK_DRIVING_CELL) "/"] 1] \
    $inc_port

set_driving_cell \
    -lib_cell [lindex [split $::env(SYNTH_CLK_DRIVING_CELL) "/"] 0] \
    -pin [lindex [split $::env(SYNTH_CLK_DRIVING_CELL) "/"] 1] \
    $dec_port

set cap_load [expr $::env(OUTPUT_CAP_LOAD) / 1000.0]
puts "\[INFO] Setting load to: $cap_load"
set_load $cap_load [all_outputs]

puts "\[INFO] Setting clock uncertainty to: $::env(CLOCK_UNCERTAINTY_CONSTRAINT)"
set_clock_uncertainty $::env(CLOCK_UNCERTAINTY_CONSTRAINT) $all_clocks

puts "\[INFO] Setting clock transition to: $::env(CLOCK_TRANSITION_CONSTRAINT)"
set_clock_transition $::env(CLOCK_TRANSITION_CONSTRAINT) $all_clocks

puts "\[INFO] Setting timing derate to: $::env(TIME_DERATING_CONSTRAINT)%"
set_timing_derate -early [expr 1-[expr $::env(TIME_DERATING_CONSTRAINT) / 100.0]]
set_timing_derate -late [expr 1+[expr $::env(TIME_DERATING_CONSTRAINT) / 100.0]]

if { [info exists ::env(OPENLANE_SDC_IDEAL_CLOCKS)] && $::env(OPENLANE_SDC_IDEAL_CLOCKS) } {
    unset_propagated_clock [all_clocks]
} else {
    set_propagated_clock [all_clocks]
}
