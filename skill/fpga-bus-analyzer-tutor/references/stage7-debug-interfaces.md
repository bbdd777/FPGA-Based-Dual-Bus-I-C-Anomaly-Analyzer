# 阶段七已验证接口与后续移植

适用当前 `G:/FPGA_test/task/task7_test` 和 `G:/stage7_mpu6050_fault_demo`。这是2026-10-12现场验证后的实现基线，设计目标仍见project-context；实际进度继续读取工程学习记录。路径、COM号、调试地址和构建版本不能自动推广到新工程。

完整接口与复现方法：[阶段七现场调试接口与移植说明](G:/FPGA_test/task/task7_test/docs/阶段七_现场调试接口与移植说明.md)。完整命名例化：[任务接口及调用说明](G:/FPGA_test/task/task7_test/阶段七_任务接口及调用说明.md)。以下保留移植时影响决策的关键契约，完整探针、字段偏移和设备步骤按需读工程文档。

## 已验证基线

阶段七主要场景及两项补充已通过：真实START后50.08µs、地址只传3位时布防，标不完整且不输出伪valid；下一实际START恢复。完整读以同笔连续UART线路、20个ILA源事件和MCU局部Data[14]核对，14/14一致、ACK×13/NACK×1，耗时2.0541ms。SCL现场约77.28kHz，属于目标不超过100kHz；不是把配置目标当实测值。

[主要现场报告](G:/FPGA_test/task/task7_test/verification/hardware_mpu6050/20261012_1029_run01/阶段七_现场检验报告.md)与[补充报告](G:/FPGA_test/task/task7_test/verification/hardware_mpu6050/20261012_1112_supplement/阶段七_补充检验报告.md)为证据入口。两份报告共同关闭阶段七；阶段八和V1仍未完成。

## 复用层和控制

- 同板复现用task7_top；新顶层复用完整路径用i2c_analyzer；已有同步/采样/编号的系统可仅复用i2c_monitor。analyzer吃原始SCL/SDA并已内含两级同步，monitor吃已同步电平；不能不加区分地重复同步。
- 当前50MHz、sample_ce每5拍、一拍宽；ADDR_WIDTH默认15、支持8～15；UART115200/8N1。analyzer未透传全部时钟/周期参数，改时钟或采样率要联动下层UART CLK_FREQ、采样周期元数据、消抖和规则阈值。
- arm_pulse/manual_trigger为同步的一系统拍请求；capture_clear才表示布防接受。仅空闲接受新布防，首次触发后保持原因，上传结束回空闲；当前需要KEY1重新布防。自动布防不是现有功能或I2C的强制要求。
- 当前analyzer/capture_uart没有通用故障输入，只含manual_trigger与addr_nack_trigger。正常读末data_valid+nack不触发地址故障；地址NACK同沿竞争优先于手动，早先已锁定的手动原因保持。
- monitor_en=capture_active：只有布防至后采样期间解析，冻结/上传有监测空窗。32784字节上传约2.85秒，第四灯亮是上传时长。

## 结果和编号

addr[6:0]/rw/nack与addr_valid一起读；data[7:0]/nack与data_valid一起读。START/STOP/restart/valid/incomplete均一系统拍20ns，下游每sys_clk判断，不能再与sample_ce相与。无valid时的保持字段不是新结果。

sample_id是下一实际写入样点的32位编号，capture_clear归0，capture_write时递增；trigger_sample_id是首次触发源编号。event_sample_id随事件保存造成它的样点编号，不能用valid公布拍的当前sample_id替代。它们与RAM地址、最终包内索引不同。

地址NACK采样沿sample_id=K、addr_nack_trigger=1、trigger_sample=1；下一20ns沿addr_valid/nack=1、event_sample_id=K，而sample_id已K+1。移植必须保留同沿请求，不改用迟到的addr_valid&&nack。

同轮映射：`delta=((event_id-trigger_id+2^31) mod 2^32)-2^31`，`j=trigger_index+delta`，0≤j<N才属于窗口。不能跨clear拼编号。UART不发送源编号；当前ILA无独立trigger_sample_id探针，在trigger_sample有效采样拍读取sample_id作为K。

## ILA与UART的不同位序

ILA 8探针宽度16/8/8/32/32/16/8/3；probe1拆addr、rw。debug_flags位15～0：START、STOP、Sr、addr_valid、data_valid、nack、incomplete、in_transaction、addrNACK、capture_clear、capture_active、capture_armed、trigger_sample、sample_ce、SCL、SDA。

**ILA flags低2位是bit1=SCL、bit0=SDA；UART样点低2位是bit1=SDA、bit0=SCL。** 必须转换后比较。

ILA8192个50MHz拍只有163.84µs；64×128或32×256窗口可记录完整事件链，窗间空白不能拼成连续原始线路。CSV信号列十六进制，索引/TRIGGER十进制；窗口索引回0意味着断段。清旧条件，确认新的采集完成后才upload，避免导出旧捕获。

Vivado2018.3已实测事件OR用neq掩码：`00000XXXXXXXXXXX`匹配5种协议事件，`00000XXXX0XXXXXX`再OR capture_clear；eq `XXXXXXXXX1XXXXXX`匹配接受布防。要包含复位后的首事件，先让MCU空闲并复位FPGA，再run ILA，最后启动MCU事务，不能在持续事件中等人复位。wait_on_hw_ila的timeout单位是分钟。

UART版本01，通道03，period100ns，多字节小端，一样点一字节；包长N+16、SUM8覆盖版本至最后负载，排除AA55和校验自身。i=min(前史,16384)、N=i+16384，触发样点算后窗首点，满窗32768点/i16384。没有UART布防命令、协议事件流或自动重新布防。COM3为本次CH340串口；COM7不是JTAG目标，后续重新枚举。

## 受控取证方法

自然按键没有落在事务中间就记未覆盖。需精确时刻时可在独立诊断顶层增加一拍内部请求，复用原核心、保持SCL/SDA纯输入，先验证夹具；结束恢复正式bit/匹配ltx。这里的MODE1真实START后500点布防、MODE2正常3B读首数据ACK后保存，只是本次取证方法，不强制每次调试重建诊断bit，也不移入正式产品控制。

无外部参考时可用已有ST-Link：独立调试工程关闭自动下载，LOAD NOCODE INCREMENTAL只载符号；读之前停CPU，准备FPGA后完整运行至ReadBuffer返回、STOP完成之后，保存局部Data[14]再恢复。不得在目标传输中间断点干扰待比较事务。PC/SP及数组位置由当前AXF反汇编确认，本次0x08000A66/SP0x20000640不能跨编译版本复用。OLED六轴值不含全部14字节参考。

检查器、控制器与API用法都在补充证据目录；需要重用时读对应源码并重新确认安装路径、设备和ABI，不把历史脚本当普遍可直接执行的接口。

## 下一阶段接入

SCL低0.5ms触发尚未接入。新规则共享scl_sync/sample_ce，100ns时阈值5000点；capture_clear清轮次，SCL恢复高清低计数；明确阈值命中点及同源编号。首次原因不能被后采样或上传期间新请求覆盖。

新增低超时需要扩展analyzer/capture_uart的请求与原因仲裁，不能接manual_trigger而误报01。原因03可作为后续约定，当前正式RTL没有产生03；电脑显示名称、ILA及检查同步更新。字段/打包变化则联动协议版本与解析器。阶段七回归保留地址NACK同沿、读末NACK不误触发、截断/中途布防恢复、首次原因及满/短窗公式，再验证新阈值边界和真实三场景。

后续用户明确要求优先；本参考不自动授予下载、调试或新功能范围。新工程读实际源/约束/构建报告，重新确认板级电平和bit/ltx，按实测维护学习记录。
