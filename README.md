# I²C Sentinel · FPGA 双路 I²C 总线异常分析仪

四路50MSa/s同步采样，20ns统一时基，262144点环形缓存；双路协议解析、低电平监测、故障关联与BRAM并行工作。MCU执行主备读取，FPGA旁路监听，电脑显示、归档和重放。200Mbit/s为内部采样位流；UART为1Mbaud，上传事件与冻结波形。

**English introduction**

I²C Sentinel is an FPGA-based dual-bus I²C anomaly analyzer built on the AMD Artix-7 platform. It synchronously samples four channels at 50 MSa/s per channel, providing 20 ns time resolution. FPGA hardware parallelism enables simultaneous protocol decoding, anomaly detection, fault correlation, and waveform buffering across both buses. By passively monitoring bus activity, the system detects address NACKs and SCL-low timeouts and verifies MCU-controlled failover between primary and backup devices. A companion PC application provides waveform visualization, event logging, and offline replay to support bus fault diagnosis and communication reliability verification.

本包于2026年10月27日同步上位机最新故障自动跟随修复，新增4项回归；当前31项单元及配套检查见[更新与验证](docs/pc_update_20261027.md)。

## 阅读入口

- [设计报告与实测图](report/design_report.md)
- [实现说明](docs/design.md) · [04协议](docs/protocol_04.md)
- [数据与证据索引](report/evidence_index.md) · [仿真结果](sim/results/README.md)
- [AI协作精选](report/ai_collaboration.md) · [176条对话正文](report/ai_conversations.md) · [可复用Skill](skill/README.md)

## 目录

| 目录 | 保留内容 |
|---|---|
| src/vivado_prj | RTL、XDC、8组testbench、构建脚本 |
| src/mcu | Keil工程、实际编译源文件、依赖头文件 |
| src/pc | 正式上位机和测试代码、锁定依赖 |
| board/firmware | 正式FPGA bit和MCU hex |
| build | 构建入口及资源/时序/DRC三份报告 |
| data | 100轮记录、性能统计、验证汇总、版本对比四张CSV |
| report | Markdown报告、9张必要配图、资料索引、协作精选和176条可见对话正文 |
| sim | 仿真入口、8份最终通过日志和结果汇总 |
| tools | PC检查入口 |
| skill | FPGA学习指导、工程证据与验证两个Skill及配套参考 |

2026年10月21日：M1/M2/M3各20/40/40，100份完整捕获；B100轮及正常A20轮均与同轮MCU14字节一致。正常区间CRC、帧序、重组及七路FIFO丢失均0。完整波形接收平均1.660386s，为电脑批次计时，不是TX线端测时。

本精简版仅保留8份最终仿真自检日志，不附原始串口流、逐点样本、大量历史调试日志或工具缓存。完整证据在队伍本地归档保留；四张表和配图用于展示结果。源码可重建，仿真流运行时生成；完整历史实测数据不在仓库中，不能仅凭表格重新解码100轮原始波形。

## 运行与重建

**Windows双击启动：**先完整解压ZIP，双击根目录的[启动上位机.bat](启动上位机.bat)。首次运行自动建立本包`.venv`并联网安装依赖；以后直接启动。电脑需先安装Python 3.10～3.12（推荐3.12，包含pip与Tkinter），仅运行上位机不需要Vivado/Keil。界面打开后选择串口、1000000波特率，点击“连接监测”。详见[使用说明](上位机使用说明.txt)。

工具：Vivado2018.3、Keil ARMCC5.06 update5、Python3.10或已验证的3.12。首次在根目录建立环境：

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r ./src/pc/requirements-lock.txt
./tools/check_pc.ps1 -PythonExe "$PWD/.venv/Scripts/python.exe" -UnitOnly
./tools/run_pc.ps1 -PythonExe "$PWD/.venv/Scripts/python.exe"
```

完整离线检查先运行仿真生成流，再检查PC。构建入口只编译，不下载硬件：

```powershell
./sim/run_sim.ps1 -VivadoBin 'C:/Xilinx/Vivado/2018.3/bin'
./tools/check_pc.ps1 -PythonExe "$PWD/.venv/Scripts/python.exe"
./build/build_fpga.ps1 -VivadoBin 'C:/Xilinx/Vivado/2018.3/bin'
./build/build_mcu.ps1 -Uv4Path 'C:/Keil_v5/UV4/UV4.exe' -FromElfPath 'C:/Keil_v5/ARM/ARMCC/bin/fromelf.exe' -PythonExe "$PWD/.venv/Scripts/python.exe"
```

将示例路径换成本机路径。生成的project、verification、objects、listings和Python缓存由`.gitignore`排除。构建与测试会重新生成这些文件，不需要提交它们。

接线：A为MPU6050/PB10、PB11，B为MPU6500/PB13、PB14；FPGA A监听L13、M13，B监听M16、M15，TX为N17，共地且使用兼容3.3V逻辑。以实际板卡方向核对，操作和规则见实现说明。

历史英文目录复现通过8组RTL、FPGA实现、MCU编译及27项PC单元和配套回归，范围见[历史范围与本次PC验证](docs/pc_update_20261027.md)。本次同步PC修复并进行离线检查，不新增上板结论。当前文件校验见[checksums.sha256](checksums.sha256)。

自研部分发布协议与作者信息由权利人填写；项目仓库：[GitHub](https://github.com/bbdd777/FPGA-Based-Dual-Bus-I-C-Anomaly-Analyzer)。
