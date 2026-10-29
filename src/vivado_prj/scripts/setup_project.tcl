# 只创建/更新离线工程，不连接硬件管理器。
set task_root [file normalize [file join [file dirname [info script]] ..]]
set task_project [file join $task_root project task_last.xpr]
if {[file exists $task_project]} {
    open_project $task_project
} else {
    create_project task_last [file join $task_root project] -part xc7a100tfgg484-2
}
set_property target_language Verilog [current_project]
set_property default_lib xil_defaultlib [current_project]
foreach task_file [glob [file join $task_root rtl *.v]] {
    if {[llength [get_files -quiet $task_file]] == 0} {add_files -norecurse $task_file}
}
foreach task_file [glob [file join $task_root sim *.v]] {
    if {[llength [get_files -quiet $task_file]] == 0} {add_files -fileset sim_1 -norecurse $task_file}
}
set task_xdc [file join $task_root constr task_last.xdc]
if {[llength [get_files -quiet $task_xdc]] == 0} {add_files -fileset constrs_1 $task_xdc}
set_property top task_last_top [get_filesets sources_1]
set_property top tb_analyzer_core [get_filesets sim_1]
set_property generic UART_BPS=1000000 [get_filesets sources_1]
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1
