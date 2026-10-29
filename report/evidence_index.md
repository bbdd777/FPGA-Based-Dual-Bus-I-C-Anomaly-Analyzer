# 结论与资料索引

本精简版保留关键表格、实测图和构建报告；原始串口流、逐点样本及完整调试日志在队伍完整归档中保留，未放入此仓库。统计表用于展示既有结果，不代替原始数据复算。

| 编号 | 本仓库入口 | 用途 |
|---|---|---|
| E01 | [实现说明](../docs/design.md)、[RTL](../src/vivado_prj/rtl/) | 并行采样、解析、规则、缓存和接口 |
| E02 | [04协议](../docs/protocol_04.md) | 位序、CRC、事件和捕获语义 |
| E03 | [验证汇总](../data/test_summary.csv)、[性能统计](../data/performance_summary.csv) | 既有实物场景、反例、恢复和量化结果 |
| E04 | [100轮记录](../data/rounds_100.csv) | 模式20/40/40、逐轮结果、样点摘要；不含原始波形文件 |
| E05 | [资源](../build/reports/utilization.rpt)、[时序](../build/reports/timing.rpt)、[DRC](../build/reports/drc.rpt) | 最终实现的原始工具报告 |
| E06 | [8组结果与最终日志](../sim/results/README.md)、[testbench](../src/vivado_prj/sim/) | 保留最终通过证据，hex串流及中间文件运行时生成 |
| E07 | [PC更新与历史验证范围](../docs/pc_update_20261027.md)、[PC测试](../src/pc/tests/) | 历史27项；本次31项及配套回归；完整实测流外置 |
| E08 | [AI协作精选](ai_collaboration.md)、[176条可见对话正文](ai_conversations.md) | 三个真实案例及原始消息正文，消息ID可跳转定位 |
| E09 | [版本对比](../data/version_comparison.csv) | 性能和资源取舍；不同功能版本，不冒充等功能优化 |
| E10 | [文件校验](../checksums.sha256)、[PC更新与历史验证范围](../docs/pc_update_20261027.md) | 当前精简文件校验与历史复现结果 |
