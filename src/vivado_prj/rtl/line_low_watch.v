`timescale 1ns / 1ps

// 连续LOW_LIMIT个同步低样点确认一次；恢复高才允许下一次事件。
// 50MSa/s的500us是25000点，不能沿用旧13位计数器。
module line_low_watch #(
    parameter integer LOW_LIMIT = 25000
) (
    input  wire        sys_clk,
    input  wire        rst_n,
    input  wire        scl,
    input  wire [63:0] sample_tick,
    output reg         valid,
    output reg  [63:0] event_tick
);
    reg [31:0] low_count;
    reg reported;
    always @(posedge sys_clk or negedge rst_n) begin
        if (!rst_n) begin
            low_count <= 0;
            reported  <= 0;
            valid     <= 0;
            event_tick <= 0;
        end else begin
            valid <= 0;
            if (scl) begin
                low_count <= 0;
                reported <= 0;
            end else if (!reported) begin
                // 首个低点的旧计数为0；第N个低点旧计数为N-1。
                if (low_count == LOW_LIMIT - 1) begin
                    valid      <= 1;
                    event_tick <= sample_tick;
                    reported   <= 1;
                end else begin
                    low_count <= low_count + 1'b1;
                end
            end
        end
    end
endmodule
