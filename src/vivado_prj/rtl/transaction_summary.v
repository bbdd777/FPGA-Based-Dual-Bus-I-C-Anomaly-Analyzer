`timescale 1ns / 1ps

// 按STOP发布一份事务摘要；重复START保留寄存器指针，再接收读出的数据。
// 完整传感器读取必须符合：68W ACK、3B ACK、重复START、68R ACK、
// 14字节、前13字节ACK、末字节主机NACK、STOP。仅地址ACK不算完整读取。
// 最多保存32字节；超长、截断和不完整组合仍可发布，但不会标为full_read。
module transaction_summary #(
    parameter [7:0] BUS_ID = 8'd0
) (
    input  wire         sys_clk,
    input  wire         rst_n,
    input  wire         start_pulse,
    input  wire         restart_pulse,
    input  wire         stop_pulse,
    input  wire         incomplete_pulse,
    input  wire         addr_valid,
    input  wire [6:0]   addr,
    input  wire         rw,
    input  wire         nack,
    input  wire         data_valid,
    input  wire [7:0]   data,
    input  wire [63:0]  event_tick,

    output reg          valid,
    output reg          full_read,
    output reg  [63:0]  stop_tick,
    output reg  [639:0] payload
);
    reg active;
    reg bad;
    reg writing;
    reg reading;
    reg prepared;
    reg [6:0] address;
    reg direction;
    reg [7:0] pointer;
    reg [5:0] count;
    reg [255:0] bytes;
    reg [31:0] nack_mask;
    reg [63:0] first_tick;
    reg [31:0] transaction_id;
    wire complete = active && prepared && reading && (address == 7'h68) &&
                    (count == 14) && (nack_mask == 32'h00002000) &&
                    !bad && !incomplete_pulse;

    // 脉冲每拍默认清零。数组不采用循环复位，32字节存为一个明确信息寄存器。
    always @(posedge sys_clk or negedge rst_n) begin
        if (!rst_n) begin
            active         <= 0;
            bad            <= 0;
            writing        <= 0;
            reading        <= 0;
            prepared       <= 0;
            address        <= 0;
            direction      <= 0;
            pointer        <= 0;
            count          <= 0;
            bytes          <= 0;
            nack_mask      <= 0;
            first_tick     <= 0;
            transaction_id <= 0;
            valid          <= 0;
            full_read      <= 0;
            stop_tick      <= 0;
            payload        <= 0;
        end else begin
            valid     <= 0;
            full_read <= 0;
            if (incomplete_pulse) begin
                bad <= 1;
            end
            if (start_pulse) begin
                active     <= 1;
                bad        <= incomplete_pulse;
                writing    <= 0;
                reading    <= 0;
                prepared   <= 0;
                pointer    <= 0;
                count      <= 0;
                bytes      <= 0;
                nack_mask  <= 0;
                first_tick <= event_tick;
            end else if (restart_pulse) begin
                // 重复START前必须只有一个已应答的3B指针字节。
                prepared <= active && writing && (address == 7'h68) &&
                            (count == 1) && (pointer == 8'h3b) &&
                            (nack_mask == 0) && !bad;
                writing   <= 0;
                reading   <= 0;
                count     <= 0;
                bytes     <= 0;
                nack_mask <= 0;
            end
            if (addr_valid && active) begin
                address   <= addr;
                direction <= rw;
                writing   <= !rw && !nack;
                reading   <= rw && !nack;
                if (nack || (rw && !prepared)) begin
                    bad <= 1;
                end
            end
            if (data_valid && active) begin
                if (count < 32) begin
                    bytes[count*8 +: 8] <= data;
                    nack_mask[count] <= nack;
                    count <= count + 1'b1;
                end else begin
                    bad <= 1;
                end
                if (writing && count == 0) begin
                    pointer <= data;
                end
            end
            if (stop_pulse && active) begin
                valid          <= 1;
                full_read      <= complete;
                stop_tick      <= event_tick;
                transaction_id <= transaction_id + 1'b1;
                active         <= 0;
                payload        <= 0;
                payload[7:0]   <= BUS_ID;
                payload[15:8]  <= {1'b0, address};
                payload[23:16] <= {7'd0, direction};
                payload[31:24] <= {5'd0, (reading && count != 0 && nack_mask[count-1]),
                                   complete, (bad || incomplete_pulse)};
                payload[39:32] <= pointer;
                payload[47:40] <= {2'd0, count};
                payload[127:64] <= first_tick;
                payload[191:128] <= event_tick;
                payload[447:192] <= bytes;
                payload[479:448] <= nack_mask;
                payload[511:480] <= event_tick - first_tick;
                payload[543:512] <= transaction_id + 1'b1;
            end
        end
    end
endmodule
