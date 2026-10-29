`timescale 1ns / 1ps

// 功能：被动监听一条7位地址I2C总线，不产生SCL、SDA或ACK。
// 前提：SCL/SDA已两级同步；所有逻辑使用sys_clk，sample_ce只是采样许可。
// 本版面向400kHz单控制器总线，50MSa/s逐拍处理；每个字节按高位先到，在第9位同时公布数据和应答。
// 普通事件/valid高一个系统时钟周期；addr_nack_trigger是本采样沿之前可用的请求。
// 无START的片段不猜地址；低电平停顿本身不算截断，超时策略由其他模块处理。
module i2c_monitor (
    input  wire        sys_clk,          // 50MHz系统时钟
    input  wire        rst_n,            // 低有效，顶层同步释放
    input  wire        sample_ce,        // 本沿处理一个同步样点
    input  wire        monitor_en,       // 持续解析，与波形冻结及上传无关
    input  wire        monitor_clear,    // 仅复位清理使用，捕获及上传不清解析器
    input  wire        scl_sync,         // 已同步的SCL，纯输入
    input  wire        sda_sync,         // 已同步的SDA，纯输入
    input  wire [63:0] sample_id,        // 当前样点编号，与RAM写入共用

    output reg         start_pulse,      // 普通START，一系统拍
    output reg         stop_pulse,       // STOP，一系统拍
    output reg         restart_pulse,    // 事务内重复START，一系统拍
    output reg  [6:0]  addr,             // 地址，应在addr_valid时读取
    output reg         rw,               // 0写、1读，与地址一起有效
    output reg         addr_valid,       // 地址及其第9位应答已完整
    output reg  [7:0]  data,             // 数据，应在data_valid时读取
    output reg         data_valid,       // 数据及其第9位应答已完整
    output reg         nack,             // 0=ACK，1=NACK，与相应valid一起读取
    output wire        addr_nack_trigger,// 地址第9位NACK的同沿捕获请求
    output reg         incomplete_pulse, // 部分字节提前结束/窗口截断/可识别的中途布防
    output reg  [63:0] event_sample_id,   // 本次事件源样点，事件无效时保持
    output reg         in_transaction,   // 已看到START，尚未看到STOP
    output wire [2:0]  decode_state      // 状态观察接口，便于ILA和仿真
);

    // ---------------- 参数与内部信号 ----------------
    localparam [2:0] WAIT_START = 3'd0; // 不解释无地址的片段
    localparam [2:0] ADDR_BITS  = 3'd1; // 接收地址字节的8位
    localparam [2:0] ADDR_ACK   = 3'd2; // 单独等待第9位
    localparam [2:0] DATA_BITS  = 3'd3; // 接收数据字节的8位
    localparam [2:0] DATA_ACK   = 3'd4; // 单独等待第9位
    localparam [2:0] WAIT_END   = 3'd5; // NACK后只等STOP或重复START

    reg  [2:0]  state;
    reg  [2:0]  bit_cnt;                // 已收0～7位，第8位时旧值为7
    reg  [7:0]  shift_data;             // 八位移位寄存器，不能拿第8位当应答
    reg         prev_scl;
    reg         prev_sda;
    reg         sample_primed;           // 第一组样点只建立比较基准
    reg  [63:0] last_sample_id;         // 窗口结束时对应最后真正采到的点
    wire        scl_rise;
    wire        start_detect;
    wire        stop_detect;
    wire        partial_byte;

    assign decode_state = state;
    assign scl_rise = sample_primed && !prev_scl && scl_sync;
    // 两次采样SCL都为高，才把SDA变化解释为START/STOP。
    // SCL与SDA同一组样点一起上升时，不能误报STOP。
    assign start_detect = sample_primed && prev_scl && scl_sync &&
                          prev_sda && !sda_sync;
    assign stop_detect  = sample_primed && prev_scl && scl_sync &&
                          !prev_sda && sda_sync;
    // 完整应答后，为产生STOP/重复START也需要先把SCL拉高。
    // 该上升沿暂时像下一字节第1位：STOP准备位为0，重复START准备位为1。
    // 随后的边界证实它是准备位时丢弃，不能把每次正常STOP都报成截断。
    assign partial_byte = (state == ADDR_BITS) || (state == ADDR_ACK) ||
                          (state == DATA_ACK) ||
                          ((state == DATA_BITS) && (bit_cnt != 3'd0) &&
                           !((bit_cnt == 3'd1) &&
                             ((stop_detect && !shift_data[0]) ||
                              (start_detect && shift_data[0]))));

    // 此请求必须在第9位采样沿前成立，缓存就在同一沿保存触发点。
    // 若用下面的寄存器addr_valid再触发，会被旧控制器推迟到下一sample_ce。
    // 请求只供同一sys_clk域使用，不能当新时钟，也不能直接驱动总线。
    assign addr_nack_trigger = rst_n && monitor_en && !monitor_clear &&
                               sample_ce && scl_rise &&
                               (state == ADDR_ACK) && sda_sync;

    // ---------------- 主逻辑：事件与协议状态 ----------------
    // 每个系统拍先清脉冲；只在命中的采样沿重新置1，因此不会保持5拍。
    // 状态、位计数和移位值共同解释同一个样点，放在同一块处理。
    always @(posedge sys_clk or negedge rst_n) begin
        if (!rst_n) begin
            state            <= WAIT_START;
            bit_cnt          <= 3'd0;
            shift_data       <= 8'd0;
            prev_scl         <= 1'b1;
            prev_sda         <= 1'b1;
            sample_primed    <= 1'b0;
            last_sample_id   <= 64'd0;
            in_transaction   <= 1'b0;
            start_pulse      <= 1'b0;
            stop_pulse       <= 1'b0;
            restart_pulse    <= 1'b0;
            addr             <= 7'd0;
            rw               <= 1'b0;
            addr_valid       <= 1'b0;
            data             <= 8'd0;
            data_valid       <= 1'b0;
            nack             <= 1'b0;
            incomplete_pulse <= 1'b0;
            event_sample_id  <= 64'd0;
        end else begin
            start_pulse      <= 1'b0;
            stop_pulse       <= 1'b0;
            restart_pulse    <= 1'b0;
            addr_valid       <= 1'b0;
            data_valid       <= 1'b0;
            incomplete_pulse <= 1'b0;
            if (monitor_clear) begin
                state           <= WAIT_START;
                bit_cnt         <= 3'd0;
                shift_data      <= 8'd0;
                sample_primed   <= 1'b0;
                in_transaction  <= 1'b0;
                last_sample_id  <= 64'd0;
                event_sample_id <= 64'd0;
                addr            <= 7'd0;
                rw              <= 1'b0;
                data            <= 8'd0;
                nack            <= 1'b0;
            end else if (!monitor_en) begin
                // 停止采集而事务仍开着，报告一次窗口截断，不能继续拼旧字节。
                // 本沿没有新样点，使用最后的真实编号，而非已经加1的sample_id。
                if (sample_primed && in_transaction) begin
                    incomplete_pulse <= 1'b1;
                    event_sample_id  <= last_sample_id;
                end
                state          <= WAIT_START;
                bit_cnt        <= 3'd0;
                sample_primed  <= 1'b0;
                in_transaction <= 1'b0;
            end else if (sample_ce) begin
                prev_scl       <= scl_sync;
                prev_sda       <= sda_sync;
                last_sample_id <= sample_id;
                if (!sample_primed) begin
                    sample_primed <= 1'b1;
                    // 低电平初始片段可能从事务中间接入；只标记、不猜地址。
                    // 初始两线都高也可能是字节中的高位，仍必须等待真实START。
                    if (!scl_sync || !sda_sync) begin
                        incomplete_pulse <= 1'b1;
                        event_sample_id  <= sample_id;
                    end
                end else if (start_detect) begin
                    if (in_transaction) begin
                        restart_pulse <= 1'b1;
                        if (partial_byte) begin
                            incomplete_pulse <= 1'b1;
                        end
                    end else begin
                        start_pulse <= 1'b1;
                    end
                    event_sample_id <= sample_id;
                    in_transaction  <= 1'b1;
                    state           <= ADDR_BITS;
                    bit_cnt         <= 3'd0;
                    shift_data      <= 8'd0;
                end else if (stop_detect) begin
                    stop_pulse      <= 1'b1;
                    event_sample_id <= sample_id;
                    if (in_transaction && partial_byte) begin
                        incomplete_pulse <= 1'b1;
                    end
                    state          <= WAIT_START;
                    bit_cnt        <= 3'd0;
                    in_transaction <= 1'b0;
                end else if (scl_rise) begin
                    case (state)
                        ADDR_BITS, DATA_BITS: begin
                            shift_data <= {shift_data[6:0], sda_sync};
                            if (bit_cnt == 3'd7) begin
                                bit_cnt <= 3'd0;
                                state   <= (state == ADDR_BITS) ? ADDR_ACK : DATA_ACK;
                            end else begin
                                bit_cnt <= bit_cnt + 3'd1;
                            end
                        end
                        ADDR_ACK: begin
                            addr            <= shift_data[7:1];
                            rw              <= shift_data[0];
                            nack            <= sda_sync;
                            addr_valid      <= 1'b1;
                            event_sample_id <= sample_id;
                            // 地址没有应答时不把后续片段当正常数据。
                            state <= sda_sync ? WAIT_END : DATA_BITS;
                        end
                        DATA_ACK: begin
                            data            <= shift_data;
                            nack            <= sda_sync;
                            data_valid      <= 1'b1;
                            event_sample_id <= sample_id;
                            // 读末NACK是正常结束；写数据NACK也不冒充地址NACK。
                            state <= sda_sync ? WAIT_END : DATA_BITS;
                        end
                        WAIT_START, WAIT_END: begin
                            // 不接收无START或NACK后的匿名字节。
                        end
                        default: begin
                            state          <= WAIT_START;
                            in_transaction <= 1'b0;
                        end
                    endcase
                end
            end
        end
    end
endmodule

