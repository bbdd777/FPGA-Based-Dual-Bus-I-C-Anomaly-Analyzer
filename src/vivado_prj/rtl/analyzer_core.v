`timescale 1ns / 1ps

// 最终分析仪数据通路。解析器、低超时、事务记录始终运行；只有原始RAM会冻结。
// UART只能分段上传原始波形；RAM忙时的抓拍请求会计入missed_triggers。
// 七个独立FIFO：A摘要/B摘要/A故障/B故障/关联结果/读取结果/状态配置。
module analyzer_core #(
    parameter integer ADDR_WIDTH = 18,
    parameter integer UART_BPS = 1_000_000,
    parameter integer LOW_LIMIT = 25000,
    parameter integer WINDOW_TICKS = 50000,
    parameter integer READ_TICKS = 100000,
    parameter integer STATUS_TICKS = 50_000_000
) (
    input  wire         sys_clk,
    input  wire         rst_n,
    input  wire         scl_a_in,
    input  wire         sda_a_in,
    input  wire         scl_b_in,
    input  wire         sda_b_in,
    output wire         tx,
    output wire [3:0]   led,
    output wire         debug_byte_valid,
    output wire [7:0]   debug_byte_data
);
    reg [63:0] sample_tick;
    wire [3:0] samples;
    wire [1:0] starts, restarts, stops, incomplete;
    wire [1:0] addr_valid, data_valid, rw, nack, low_valid;
    wire [6:0] addr [0:1];
    wire [7:0] data [0:1];
    wire [63:0] event_tick [0:1];
    wire [63:0] low_tick [0:1];
    wire [1:0] summary_valid, full_read;
    wire [63:0] stop_tick [0:1];
    wire [639:0] summary [0:1];
    wire [1:0] address_fault = addr_valid & nack;
    wire a_fault = (address_fault[0] && addr[0] == 7'h6a && !rw[0]) || low_valid[0];
    wire b_ack = addr_valid[1] && addr[1] == 7'h68 && !rw[1] && !nack[1];
    wire waiting;
    wire corr_valid, result_valid, rule_trigger;
    wire [63:0] corr_tick, result_tick;
    wire [639:0] corr_payload, result_payload;
    wire [7:0] rule_reason;
    wire [31:0] rule_link, ignored_faults;

    wire capture_ready, frozen, upload_done, ram_valid, ram_en;
    wire [ADDR_WIDTH-1:0] ram_offset;
    wire [3:0] ram_data;
    wire [31:0] capture_id, sample_count, trigger_index, correlation_id, missed;
    wire [63:0] trigger_tick, first_tick;
    wire [7:0] reason;
    wire normal_trigger = summary_valid[1] && full_read[1] && !waiting && !rule_trigger && !a_fault;

    wire [6:0] fifo_valid;
    wire [711:0] fifo_head [0:6];
    wire [31:0] drops [0:6];
    wire [5:0] peaks [0:6];
    reg [6:0] fifo_pop;
    reg [2:0] next_source;
    reg [2:0] selected_source;
    reg selected_valid;
    reg [711:0] selected_record;
    wire event_pop;
    integer scan_index;
    integer candidate;

    reg [31:0] status_count;
    reg config_pending;
    reg status_push;
    reg [711:0] status_record;
    reg [31:0] accepted_captures;
    reg previous_ready;

    wire frame_valid, frame_ready, frame_done;
    wire [7:0] frame_kind;
    wire [63:0] frame_tick;
    wire [31:0] frame_capture;
    wire [15:0] frame_length;
    wire [1087:0] frame_payload;
    wire byte_valid, uart_busy;
    wire [7:0] byte_data;

    assign led = {waiting, frozen, capture_ready, rst_n};
    assign debug_byte_valid = byte_valid && !uart_busy;
    assign debug_byte_data = byte_data;

    // 全工程唯一时间轴：每拍20ns。64位不会在旧32位的85.9秒处回绕。
    always @(posedge sys_clk or negedge rst_n) begin
        if (!rst_n) begin
            sample_tick <= 0;
        end else begin
            sample_tick <= sample_tick + 1'b1;
        end
    end

    genvar bus_index;
    generate
        for (bus_index = 0; bus_index < 2; bus_index = bus_index + 1) begin: buses
            localparam [7:0] BUS_ID = bus_index;
            i2c_input_sync sync_inst (
                .sys_clk                 (sys_clk),
                .rst_n                   (rst_n),
                .scl_in                  (bus_index == 0 ? scl_a_in : scl_b_in),
                .sda_in                  (bus_index == 0 ? sda_a_in : sda_b_in),
                .scl_sync                (samples[bus_index*2]),
                .sda_sync                (samples[bus_index*2+1])
            );
            i2c_monitor monitor_inst (
                .sys_clk                 (sys_clk),
                .rst_n                   (rst_n),
                .sample_ce               (1'b1),
                .monitor_en              (1'b1),
                .monitor_clear           (1'b0),
                .scl_sync                (samples[bus_index*2]),
                .sda_sync                (samples[bus_index*2+1]),
                .sample_id               (sample_tick),
                .start_pulse             (starts[bus_index]),
                .stop_pulse              (stops[bus_index]),
                .restart_pulse           (restarts[bus_index]),
                .addr                    (addr[bus_index]),
                .rw                      (rw[bus_index]),
                .addr_valid              (addr_valid[bus_index]),
                .data                    (data[bus_index]),
                .data_valid              (data_valid[bus_index]),
                .nack                    (nack[bus_index]),
                .addr_nack_trigger       (),
                .incomplete_pulse        (incomplete[bus_index]),
                .event_sample_id         (event_tick[bus_index]),
                .in_transaction          (),
                .decode_state            ()
            );
            line_low_watch #(.LOW_LIMIT(LOW_LIMIT)) low_inst (
                .sys_clk                 (sys_clk),
                .rst_n                   (rst_n),
                .scl                     (samples[bus_index*2]),
                .sample_tick             (sample_tick),
                .valid                   (low_valid[bus_index]),
                .event_tick              (low_tick[bus_index])
            );
            transaction_summary #(.BUS_ID(bus_index)) summary_inst (
                .sys_clk                 (sys_clk),
                .rst_n                   (rst_n),
                .start_pulse             (starts[bus_index]),
                .restart_pulse           (restarts[bus_index]),
                .stop_pulse              (stops[bus_index]),
                .incomplete_pulse        (incomplete[bus_index]),
                .addr_valid              (addr_valid[bus_index]),
                .addr                    (addr[bus_index]),
                .rw                      (rw[bus_index]),
                .nack                    (nack[bus_index]),
                .data_valid              (data_valid[bus_index]),
                .data                    (data[bus_index]),
                .event_tick              (event_tick[bus_index]),
                .valid                   (summary_valid[bus_index]),
                .full_read               (full_read[bus_index]),
                .stop_tick               (stop_tick[bus_index]),
                .payload                 (summary[bus_index])
            );
            record_fifo summary_fifo (
                .sys_clk                 (sys_clk),
                .rst_n                   (rst_n),
                .push                    (summary_valid[bus_index]),
                .push_data               ({(bus_index == 0 ? 8'h20 : 8'h21), stop_tick[bus_index], summary[bus_index]}),
                .pop                     (fifo_pop[bus_index]),
                .valid                   (fifo_valid[bus_index]),
                .head                    (fifo_head[bus_index]),
                .dropped                 (drops[bus_index]),
                .peak                    (peaks[bus_index])
            );
            // 同一路地址NACK发生在SCL上升沿，不会和持续低确认同时成立。
            wire fault_push = address_fault[bus_index] || low_valid[bus_index];
            wire [7:0] fault_kind = low_valid[bus_index] ? 8'd2 : 8'd1;
            wire [639:0] fault_payload = {608'd0, {7'd0,nack[bus_index]},
                                          {1'b0,addr[bus_index]}, fault_kind, BUS_ID};
            record_fifo fault_fifo (
                .sys_clk                 (sys_clk),
                .rst_n                   (rst_n),
                .push                    (fault_push),
                .push_data               ({(bus_index == 0 ? 8'h30 : 8'h31),
                    (low_valid[bus_index] ? low_tick[bus_index] : event_tick[bus_index]), fault_payload}),
                .pop                     (fifo_pop[bus_index+2]),
                .valid                   (fifo_valid[bus_index+2]),
                .head                    (fifo_head[bus_index+2]),
                .dropped                 (drops[bus_index+2]),
                .peak                    (peaks[bus_index+2])
            );
        end
    endgenerate

    failover_rules #(.WINDOW_TICKS(WINDOW_TICKS),
                .READ_TICKS              (READ_TICKS)) rules_inst (
        .sys_clk                 (sys_clk),
                .rst_n                   (rst_n),
                .processed_tick          (sample_tick == 0 ? 64'd0 : sample_tick - 1'b1),
        .a_fault                 (a_fault),
                .fault_kind              (low_valid[0] ? 8'd2 : 8'd1),
        .a_tick                  (low_valid[0] ? low_tick[0] : event_tick[0]),
        .b_ack                   (b_ack),
                .b_tick                  (event_tick[1]),
                .b_done                  (summary_valid[1]),
        .b_full                  (full_read[1]),
                .b_stop_tick             (stop_tick[1]),
                .waiting                 (waiting),
        .correlation_valid       (corr_valid),
                .correlation_tick        (corr_tick),
                .correlation_payload     (corr_payload),
        .read_valid              (result_valid),
                .read_tick               (result_tick),
                .read_payload            (result_payload),
        .trigger_valid           (rule_trigger),
                .trigger_reason          (rule_reason),
                .trigger_link            (rule_link),
        .ignored_faults          (ignored_faults)
    );
    record_fifo correlation_fifo (
        .sys_clk                 (sys_clk),
                .rst_n                   (rst_n),
                .push                    (corr_valid),
        .push_data               ({8'h32,corr_tick,corr_payload}),
                .pop                     (fifo_pop[4]),
        .valid                   (fifo_valid[4]),
                .head                    (fifo_head[4]),
                .dropped                 (drops[4]),
                .peak                    (peaks[4])
    );
    record_fifo result_fifo (
        .sys_clk                 (sys_clk),
                .rst_n                   (rst_n),
                .push                    (result_valid),
        .push_data               ({8'h33,result_tick,result_payload}),
                .pop                     (fifo_pop[5]),
        .valid                   (fifo_valid[5]),
                .head                    (fifo_head[5]),
                .dropped                 (drops[5]),
                .peak                    (peaks[5])
    );
    record_fifo status_fifo (
        .sys_clk                 (sys_clk),
                .rst_n                   (rst_n),
                .push                    (status_push),
                .push_data               (status_record),
        .pop                     (fifo_pop[6]),
                .valid                   (fifo_valid[6]),
                .head                    (fifo_head[6]),
        .dropped                 (drops[6]),
                .peak                    (peaks[6])
    );

    // 配置上电发送一次；之后每秒状态含各队列丢失/峰值、原始波形空窗计数。
    integer status_index;
    always @(posedge sys_clk or negedge rst_n) begin
        if (!rst_n) begin
            status_count      <= 0;
            config_pending    <= 1;
            status_push       <= 0;
            status_record     <= 0;
            accepted_captures <= 0;
            previous_ready    <= 1;
        end else begin
            status_push <= 0;
            previous_ready <= capture_ready;
            if (previous_ready && !capture_ready) begin
                accepted_captures <= accepted_captures + 1'b1;
            end
            if (config_pending || status_count == STATUS_TICKS-1) begin
                config_pending <= 0;
                status_count <= 0;
                status_push <= 1;
                status_record <= 0;
                status_record[711:704] <= config_pending ? 8'h11 : 8'h10;
                status_record[703:640] <= sample_tick;
                if (config_pending) begin
                    status_record[31:0] <= 20;
                    status_record[63:32] <= (1 << ADDR_WIDTH);
                    status_record[95:64] <= UART_BPS;
                    status_record[127:96] <= LOW_LIMIT;
                    status_record[159:128] <= WINDOW_TICKS;
                    status_record[191:160] <= READ_TICKS;
                    status_record[223:192] <= 1;
                end else begin
                    status_record[31:0] <= {30'd0,frozen,capture_ready};
                    status_record[63:32] <= missed;
                    status_record[95:64] <= accepted_captures;
                    status_record[127:96] <= ignored_faults;
                    for (status_index=0; status_index<7; status_index=status_index+1) begin
                        status_record[128+status_index*32 +: 32] <= drops[status_index];
                        status_record[352+status_index*8 +: 8] <= {2'd0,peaks[status_index]};
                    end
                    status_record[447:416] <= capture_id;
                end
            end else begin
                status_count <= status_count + 1'b1;
            end
        end
    end

    // 轮询仲裁：出队沿后从下一来源开始找；同拍多来源不会互相覆盖。
    always @(*) begin
        selected_source = 0;
        selected_valid = 0;
        selected_record = 0;
        fifo_pop = 0;
        candidate = 0;
        for (scan_index=0; scan_index<7; scan_index=scan_index+1) begin
            candidate = next_source + scan_index;
            if (candidate >= 7) begin
                candidate = candidate - 7;
            end
            if (!selected_valid && fifo_valid[candidate]) begin
                selected_valid = 1;
                selected_source = candidate;
                selected_record = fifo_head[candidate];
            end
        end
        if (event_pop && selected_valid) begin
            fifo_pop[selected_source] = 1;
        end
    end
    always @(posedge sys_clk or negedge rst_n) begin
        if (!rst_n) begin
            next_source <= 0;
        end else if (event_pop) begin
            next_source <= selected_source == 6 ? 0 : selected_source + 1'b1;
        end
    end

    capture_ring #(.ADDR_WIDTH(ADDR_WIDTH)) capture_inst (
        .sys_clk                 (sys_clk),
                .rst_n                   (rst_n),
                .sample_tick             (sample_tick),
                .sample_data             (samples),
        .trigger_valid           (rule_trigger || normal_trigger),
        .trigger_reason          (rule_trigger ? rule_reason : 8'd6),
        .correlation_id          (rule_trigger ? rule_link : 32'd0),
                .upload_done             (upload_done),
        .read_en                 (ram_en),
                .read_offset             (ram_offset),
                .ready                   (capture_ready),
                .frozen                  (frozen),
        .read_data               (ram_data),
                .read_valid              (ram_valid),
                .capture_id              (capture_id),
        .sample_count            (sample_count),
                .trigger_index           (trigger_index),
                .trigger_tick            (trigger_tick),
        .first_tick              (first_tick),
                .reason                  (reason),
                .linked_correlation      (correlation_id),
                .missed_triggers         (missed)
    );
    wave_stream #(.ADDR_WIDTH(ADDR_WIDTH)) stream_inst (
        .sys_clk                 (sys_clk),
                .rst_n                   (rst_n),
                .frozen                  (frozen),
                .capture_id              (capture_id),
        .sample_count            (sample_count),
                .trigger_index           (trigger_index),
                .trigger_tick            (trigger_tick),
        .first_tick              (first_tick),
                .reason                  (reason),
                .correlation_id          (correlation_id),
        .upload_done             (upload_done),
                .read_en                 (ram_en),
                .read_offset             (ram_offset),
        .read_valid              (ram_valid),
                .read_data               (ram_data),
                .event_valid             (selected_valid),
        .event_record            (selected_record),
                .event_pop               (event_pop),
                .frame_valid             (frame_valid),
        .frame_ready             (frame_ready),
                .frame_done              (frame_done),
                .frame_kind              (frame_kind),
        .frame_tick              (frame_tick),
                .frame_capture           (frame_capture),
                .frame_length            (frame_length),
                .frame_payload           (frame_payload)
    );
    frame_tx framer_inst (
        .sys_clk                 (sys_clk),
                .rst_n                   (rst_n),
                .frame_valid             (frame_valid),
                .frame_ready             (frame_ready),
        .kind                    (frame_kind),
                .source_tick             (frame_tick),
                .capture_id              (frame_capture),
        .payload_length          (frame_length),
                .payload                 (frame_payload),
                .byte_valid              (byte_valid),
        .byte_ready              (!uart_busy),
                .byte_data               (byte_data),
                .done                    (frame_done)
    );
    uart_tx #(.UART_BPS(UART_BPS)) uart_inst (
        .sys_clk                 (sys_clk),
                .sys_rst_n               (rst_n),
                .pi_data                 (byte_data),
                .pi_flag                 (byte_valid && !uart_busy),
        .tx                      (tx),
                .tx_done                 (),
                .tx_busy                 (uart_busy)
    );
endmodule

