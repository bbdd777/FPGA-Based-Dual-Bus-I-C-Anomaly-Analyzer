# 仿真结果汇总

验证日期：2026年10月23日。工具：Vivado Simulator 2018.3。2026年10月26日从已验证的完整归档补回本仓库；本轮没有重新执行仿真。

以下8份均为各测试最终日志，均含对应的`PASS ALL`自检标记。

| 测试 | 检查内容 | 结果 | 自检输出 | 原始日志 |
|---|---|---|---|---|
| `tb_capture_ring` | 环形缓存、触发窗口与读取 | 通过 | `PASS ALL tb_capture_ring` | [日志](tb_capture_ring.log) |
| `tb_failover_rules` | 故障关联及完整读取规则 | 通过 | `PASS ALL tb_failover_rules` | [日志](tb_failover_rules.log) |
| `tb_uart_1m` | 1Mbaud UART逐位发送 | 通过 | `PASS ALL tb_uart_1m` | [日志](tb_uart_1m.log) |
| `tb_pressure` | FIFO满队列/同拍出入队、低阈值边界和复位 | 通过 | `PASS ALL tb_pressure` | [日志](tb_pressure.log) |
| `tb_stream_1m` | 1M串流、奇数样点与发送一致性 | 通过 | `PASS ALL tb_stream_1m bytes=210` | [日志](tb_stream_1m.log) |
| `tb_live_busy` | 上传忙时继续解析及忙计数 | 通过 | `PASS ALL tb_live_busy summaries=2 missed=1` | [日志](tb_live_busy.log) |
| `tb_bad_reads` | 4类错误读取拒绝及无STOP超时 | 通过 | `PASS ALL tb_bad_reads rejected=4 read_timeout=1` | [日志](tb_bad_reads.log) |
| `tb_analyzer_core` | 整链3份完整捕获及B读取 | 通过 | `PASS ALL tb_analyzer_core captures=3 full_reads=3` | [日志](tb_analyzer_core.log) |

本目录保留约10KB的结果证据。大体积hex串流、波形数据库、重复日志和仿真工具缓存不随包保存；运行`sim/run_sim.ps1`即可重新生成。

262144点整链为缩短仿真运行时间使用加速UART；实际1Mbaud另由UART与串流激励逐位验证。仿真耗时不作为上板上传时长，仿真结果不替代实物测试。
