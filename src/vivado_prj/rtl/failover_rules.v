`timescale 1ns / 1ps

// 实时关联：A首次故障 -> 1ms内B的68/W地址ACK -> 2ms内完整14字节STOP。
// 1ms是两个源事件编号之间的间隔，等于边界成功；下一拍才判超时。
// processed_tick必须与输入事件同批，不能用消费者较晚的当前时刻代替。
module failover_rules #(
    parameter integer WINDOW_TICKS = 50000,
    parameter integer READ_TICKS = 100000
) (
    input  wire         sys_clk,
    input  wire         rst_n,
    input  wire [63:0]  processed_tick,
    input  wire         a_fault,
    input  wire [7:0]   fault_kind,
    input  wire [63:0]  a_tick,
    input  wire         b_ack,
    input  wire [63:0]  b_tick,
    input  wire         b_done,
    input  wire         b_full,
    input  wire [63:0]  b_stop_tick,

    output wire         waiting,
    output reg          correlation_valid,
    output reg  [63:0]  correlation_tick,
    output reg  [639:0] correlation_payload,
    output reg          read_valid,
    output reg  [63:0]  read_tick,
    output reg  [639:0] read_payload,
    output reg          trigger_valid,
    output reg  [7:0]   trigger_reason,
    output reg  [31:0]  trigger_link,
    output reg  [31:0]  ignored_faults
);
    reg wait_ack;
    reg wait_read;
    reg [31:0] correlation_id;
    reg [63:0] start_tick;
    reg [63:0] ack_tick;
    reg [7:0] saved_kind;
    wire new_fault = a_fault && !wait_ack && !wait_read;
    wire [63:0] origin = new_fault ? a_tick : start_tick;
    wire matched = b_ack && (wait_ack || new_fault) && (b_tick >= origin) &&
                   ((b_tick - origin) <= WINDOW_TICKS);
    wire [31:0] current_id = new_fault ? correlation_id + 1'b1 : correlation_id;
    assign waiting = wait_ack || wait_read;

    always @(posedge sys_clk or negedge rst_n) begin
        if (!rst_n) begin
            wait_ack            <= 0;
            wait_read           <= 0;
            correlation_id      <= 0;
            start_tick          <= 0;
            ack_tick            <= 0;
            saved_kind          <= 0;
            correlation_valid   <= 0;
            correlation_tick    <= 0;
            correlation_payload <= 0;
            read_valid          <= 0;
            read_tick           <= 0;
            read_payload        <= 0;
            trigger_valid       <= 0;
            trigger_reason      <= 0;
            trigger_link        <= 0;
            ignored_faults      <= 0;
        end else begin
            correlation_valid <= 0;
            read_valid        <= 0;
            trigger_valid     <= 0;
            if (a_fault && !new_fault) begin
                ignored_faults <= ignored_faults + 1'b1;
            end
            if (new_fault) begin
                wait_ack       <= 1;
                start_tick     <= a_tick;
                saved_kind     <= fault_kind;
                correlation_id <= current_id;
            end
            // 匹配优先于超时，且明确拒绝读地址ACK和窗口外的地址ACK。
            if (matched || (wait_ack && processed_tick > start_tick &&
                            processed_tick - start_tick > WINDOW_TICKS)) begin
                wait_ack          <= 0;
                correlation_valid <= 1;
                correlation_tick  <= matched ? b_tick : processed_tick;
                correlation_payload <= 0;
                correlation_payload[31:0]   <= current_id;
                correlation_payload[39:32]  <= matched ? 8'd1 : 8'd2;
                correlation_payload[47:40]  <= new_fault ? fault_kind : saved_kind;
                correlation_payload[127:64] <= origin;
                correlation_payload[191:128] <= matched ? b_tick : processed_tick;
                correlation_payload[223:192] <= (matched ? b_tick : processed_tick) - origin;
                correlation_payload[255:224] <= WINDOW_TICKS;
                trigger_valid  <= 1;
                trigger_reason <= matched ? 8'd5 : 8'd4;
                trigger_link   <= current_id;
                if (matched) begin
                    wait_read <= 1;
                    ack_tick  <= b_tick;
                end
            end
            // STOP比地址事件再经过一层摘要寄存器；先处理源STOP，再处理截止。
            // processed_tick-1与本拍b_done的事件层级一致，给合法截止STOP留足一拍。
            if (wait_read && ((b_done && b_stop_tick >= ack_tick) ||
                (processed_tick > ack_tick + READ_TICKS + 1))) begin
                wait_read <= 0;
                read_valid <= 1;
                read_tick <= b_done ? b_stop_tick : processed_tick - 1'b1;
                read_payload <= 0;
                read_payload[31:0] <= correlation_id;
                read_payload[39:32] <= (b_done && b_full &&
                    b_stop_tick - ack_tick <= READ_TICKS) ? 8'd1 :
                    ((b_done && b_stop_tick - ack_tick <= READ_TICKS) ? 8'd2 : 8'd3);
                read_payload[127:64] <= ack_tick;
                read_payload[191:128] <= b_done ? b_stop_tick : processed_tick - 1'b1;
                read_payload[223:192] <= READ_TICKS;
            end
        end
    end
endmodule
