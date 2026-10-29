# 串口协议04：实际RTL与Python接口

所有多字节整数小端。UART默认1M、8N1，FPGA只发送。每个帧均有CRC16；波形另有完整CRC32。

## 公共帧

| 偏移 | 长度 | 内容 |
|---:|---:|---|
| 0 | 2 | AA 55 |
| 2 | 1 | 04 |
| 3 | 1 | kind |
| 4 | 4 | frame_sequence，32位自然绕回 |
| 8 | 8 | source_tick，20ns单位；波形所有帧统一使用实际trigger_tick |
| 16 | 4 | capture_id；实时记录为0，波形从1开始 |
| 20 | 2 | payload_length，最大136 |
| 22 | 可变 | payload |
| 22+长度 | 2 | CRC16低字节、高字节 |

CRC16-CCITT-FALSE：poly=1021、init=FFFF、非反射、xorout=0000；覆盖version到payload末尾，**不包含AA55和CRC自身**。`123456789 -> 29B1`。

FPGA复位后首条配置帧seq=0，capture_id与64位tick重新计数。电脑建立新的session_number；既有故障归档仍保留，避免重启后的相同capture_id互相覆盖。不同来源可能排队后交错发送，不能要求source_tick按帧序严格递增。

## 类型

| kind | 负载长度 | 含义 |
|---|---:|---|
| 10 | 80 | 状态 |
| 11 | 80 | 固定配置，上电一次 |
| 20 / 21 | 80 | A / B STOP事务摘要 |
| 30 / 31 | 80 | A / B地址NACK或持续低确认 |
| 32 | 80 | 1ms地址应答关联结果 |
| 33 | 80 | 2ms完整读取结果 |
| 40 | 48 | 波形开始 |
| 41 | 8+ceil(点数/2) | 波形块，1至256点 |
| 42 | 16 | 波形结束 |

未定义的保留字段发送0。本版无80命令帧、无ARM命令。

## 波形开始40

| 负载偏移 | 类型 | 内容 |
|---:|---|---|
| 0 | u32 | period_ns=20 |
| 4 | u32 | sample_count，实际点数≤262144 |
| 8 | u32 | trigger_index，0起始 |
| 12 | u8 | reason：4关联超时、5地址ACK及时后的证据、6正常B完整读 |
| 13 | u8 | channel_map=E4，bit0/1/2/3为A SCL/A SDA/B SCL/B SDA |
| 14 | u8 | encoding=1，双样点nibble编码 |
| 15 | u8 | 保留0 |
| 16 | u64 | trigger_tick，实际接受触发请求的写入样点 |
| 24 | u64 | first_sample_tick，必须满足first+index=trigger |
| 32 | u32 | correlation_id，正常波形为0 |
| 36 | u32 | config_id=1 |
| 40 | u32 | depth=262144，测试可用256 |
| 44 | u32 | flags，bit0历史不足短窗 |

## 波形块41与结束42

块负载：offset:u32、valid_samples:u16、encoding:u8=1、reserved:u8=0、压缩数据。

offset指**样点**偏移，不是字节偏移。每字节低4位放较早样点，高4位放下一个样点；例如样点1、A、3编码为A1、03，valid_samples=3。奇数末点的高4位必须填0，且不计入样点数。块必须连续、无重复、无越界，256点块长度136字节。

结束负载：sample_count:u32、encoded_bytes:u32、wave_crc32:u32、reason:u8、reserved[3]=0。encoded_bytes=ceil(sample_count/2)。CRC32为CRC-32/ISO-HDLC，反射多项式EDB88320，init/xorout=FFFFFFFF，`123456789 -> CBF43926`。校验输入是**按时间顺序解包后的样点字节，每个字节高4位为0**，不是压缩负载。Python对应`zlib.crc32(samples)`。

收到坏CRC、缺块、重复块、错误offset、错误样点数或错误全波形CRC时不能公布完整捕获，也不能补0。串口中途连接可能收到无开始帧的块，只能等待下一份完整捕获。

## 事务摘要20/21：80字节

| 偏移 | 类型 | 内容 |
|---:|---|---|
| 0 | u8 | bus，0=A、1=B |
| 1 | u8 | 7位地址 |
| 2 | u8 | 最后一段方向，0W/1R |
| 3 | u8 | flags：bit0不完整/异常，bit1完整3B起始14字节读取，bit2最后读数据NACK |
| 4 | u8 | 寄存器指针 |
| 5 | u8 | data_count≤32；含重复START的读取只保存读出段数据 |
| 6 | 2 | 保留 |
| 8 | u64 | 本次首START源tick |
| 16 | u64 | STOP源tick |
| 24 | 32 bytes | 数据，未用位置0 |
| 56 | u32 | 数据NACK位图，1=NACK；完整14字节读取为00002000 |
| 60 | u32 | STOP-START样点间隔，32位 |
| 64 | u32 | 每路事务编号 |
| 68 | 12 | 保留 |

bit2单独置位只说明看到了最后NACK；仅bit1才表示结构满足完整读取条件。数据每两个字节为高字节在前的传感器有符号16位原始量，此为器件数据自身格式，与协议整数小端无冲突。

## 故障30/31：80字节

偏移0 bus:u8，1 fault_kind:u8（1地址NACK、2持续低），2 address:u8，3 nack:u8，其余0。持续低时地址/应答字段可能是保留的上次解码值，**必须看fault_kind，不能将其解释为本次有效地址**。源tick为第9位NACK样点或第25000个连续低样点。

## 关联32与完整读取33：各80字节

共同字段：0 correlation_id:u32；4 result:u8；8 start_tick:u64；16 end_tick:u64。

32的result：1地址ACK及时、2地址ACK超时。偏移5为起因1=NACK、2=低确认；24 elapsed_ticks:u32；28 window_ticks:u32。source_tick等于end_tick。它只给出地址应答结论，实际波形是否保存要看40帧中的correlation_id及状态中的missed_captures。

33的result：1完整读取成功、2STOP时结构不完整、3完整读超时；start为B首个68/W ACK，end为STOP或读窗口截止后的判定时刻；24 read_limit_ticks:u32=100000。源STOP在截止边界时优先处理，以抵消摘要寄存器比地址事件多一层的传递延迟。

## 配置11与状态10：各80字节

配置从偏移0开始依次为7个u32：period_ns、depth、UART_BPS配置值、LOW_LIMIT、WINDOW_TICKS、READ_TICKS、config_id；其余0。

状态：0 flags:u32（bit0滚动可接受抓拍、bit1冻结）；4 missed_captures:u32；8 accepted_captures:u32；12 ignored_faults:u32；16起7个u32为FIFO丢失；44起7个u8为FIFO峰值；51保留；52 current_capture:u32；56至79保留。

FIFO顺序：A摘要、B摘要、A故障、B故障、关联结果、完整读结果、状态配置。队列丢失与RAM忙时未保存波形为不同指标，界面分别显示。flags=0且已经收到状态表示POST采样中，并不表示解析器停止。
