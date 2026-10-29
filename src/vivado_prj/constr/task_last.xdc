# 升腾Pro XC7A100T / FGG484-2：硬件规格书V1.0.1第54页、Pro引脚绑定映射表。
# A: CN4-5 L13 / CN4-6 M13；B: CN4-7 M16 / CN4-8 M15；CN4-3公共地。
# CN4-1/2为5V，不能接入采样输入。接线时核对实物版本/方向和3.3V上拉。
create_clock -name sys_clk -period 20.000 [get_ports sys_clk]
set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]
set_property IOSTANDARD LVCMOS33 [get_ports {sys_clk sys_rst_n scl_a_in sda_a_in scl_b_in sda_b_in tx led[*]}]
set_property PACKAGE_PIN W19 [get_ports sys_clk]
set_property PACKAGE_PIN N15 [get_ports sys_rst_n]
set_property PACKAGE_PIN L13 [get_ports scl_a_in]
set_property PACKAGE_PIN M13 [get_ports sda_a_in]
set_property PACKAGE_PIN M16 [get_ports scl_b_in]
set_property PACKAGE_PIN M15 [get_ports sda_b_in]
set_property PACKAGE_PIN N17 [get_ports tx]
set_property PACKAGE_PIN M21 [get_ports {led[0]}]
set_property PACKAGE_PIN L21 [get_ports {led[1]}]
set_property PACKAGE_PIN K21 [get_ports {led[2]}]
set_property PACKAGE_PIN K22 [get_ports {led[3]}]
# 外部输入异步，仅排除引脚入口；同步寄存器之间仍检查50MHz内部时序。
set_false_path -from [get_ports {sys_rst_n scl_a_in sda_a_in scl_b_in sda_b_in}]
set_false_path -to [get_ports {tx led[*]}]
set_property SLEW SLOW [get_ports {tx led[*]}]
set_property DRIVE 8 [get_ports {tx led[*]}]

