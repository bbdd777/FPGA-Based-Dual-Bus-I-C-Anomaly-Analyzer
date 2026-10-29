# 综合、实现、时序/DRC和bitstream均为离线操作，脚本没有JTAG/下载命令。
source [file join [file dirname [info script]] setup_project.tcl]
set task_baud 1000000
if {$argc > 0} {set task_baud [lindex $argv 0]}
if {$task_baud ni {460800 921600 1000000 2000000}} {error "unsupported baud profile"}
set_property generic UART_BPS=$task_baud [get_filesets sources_1]
set task_report [file join $task_root verification build_$task_baud]
file mkdir $task_report
synth_design -top task_last_top -part xc7a100tfgg484-2 -flatten_hierarchy rebuilt
write_checkpoint -force [file join $task_report post_synth.dcp]
report_utilization -file [file join $task_report utilization_synth.rpt]
opt_design
place_design
phys_opt_design
route_design
write_checkpoint -force [file join $task_report routed.dcp]
report_timing_summary -delay_type min_max -report_unconstrained -file [file join $task_report timing.rpt]
report_utilization -file [file join $task_report utilization.rpt]
report_drc -file [file join $task_report drc.rpt]
report_cdc -file [file join $task_report cdc.rpt]
report_io -file [file join $task_report io.rpt]
set task_setup [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set task_hold [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
if {$task_setup < 0 || $task_hold < 0} {error "timing failed: setup=$task_setup hold=$task_hold"}
set task_bad_drc [get_drc_violations -quiet -filter {SEVERITY == Error || SEVERITY == {Critical Warning}}]
if {[llength $task_bad_drc]} {error "critical DRC: $task_bad_drc"}
if {[llength [get_drc_violations -quiet REQP-1839*]]} {error "asynchronous BRAM control remains"}
if {[llength [get_cells -quiet -hier -filter {IS_BLACKBOX == 1}]]} {error "black box remains"}
write_bitstream -force [file join $task_report task_last_$task_baud.bit]
set task_result [open [file join $task_report result.json] w]
puts $task_result "{\"baud\":$task_baud,\"sample_rate\":50000000,\"samples\":262144,\"setup_slack_ns\":$task_setup,\"hold_slack_ns\":$task_hold,\"hardware_tested\":false}"
close $task_result
puts "PASS OFFLINE BUILD baud=$task_baud setup=$task_setup hold=$task_hold"
close_project
