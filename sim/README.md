# 仿真

[查看8组最终仿真结果和日志](results/README.md)。这些是2026年10月23日已完成验证的归档，非本轮重新运行。

[查看8组最终仿真结果和日志](results/README.md)。这些是2026年10月23日已完成验证的归档，非本轮重新运行。

testbench保存在`src/vivado_prj/sim/`。在仓库根目录运行：

```powershell
./sim/run_sim.ps1 -VivadoBin 'C:/Xilinx/Vivado/2018.3/bin'
```

脚本检查8组：tb_capture_ring、tb_failover_rules、tb_uart_1m、tb_pressure、tb_stream_1m、tb_live_busy、tb_bad_reads、tb_analyzer_core。每组须出现`PASS ALL <模块名>`。

运行后在`src/vivado_prj/verification/sim/`生成日志及PC回放需要的五个hex流。正式深度整链使用加速UART参数；实际1M另由逐位UART测试检查，仿真时长不作为实物上传耗时。既有通过记录见`data/test_summary.csv`；本包保留`sim/results/`下8份最终自检日志，不预存hex串流及中间文件。
