`timescale 1ns / 1ps

// 每个来源独立排队。满时丢新记录并计数，不静默覆盖旧记录。
// 同拍出队可让出一个位置；地址自然绕回，因此DEPTH必须为2的幂。
module record_fifo #(
    parameter integer WIDTH = 712,
    parameter integer ADDR_WIDTH = 5
) (
    input  wire                   sys_clk,
    input  wire                   rst_n,
    input  wire                   push,
    input  wire [WIDTH-1:0]       push_data,
    input  wire                   pop,

    output wire                   valid,
    output wire [WIDTH-1:0]       head,
    output reg  [31:0]            dropped,
    output reg  [ADDR_WIDTH:0]    peak
);
    localparam integer DEPTH = 1 << ADDR_WIDTH;
    reg [WIDTH-1:0] memory [0:DEPTH-1];
    reg [ADDR_WIDTH-1:0] write_addr;
    reg [ADDR_WIDTH-1:0] read_addr;
    reg [ADDR_WIDTH:0] count;
    wire take = valid && pop;
    wire put = push && ((count < DEPTH) || take);

    assign valid = (count != 0);
    assign head = memory[read_addr];

    // 数组不复位。count=0时，旧数组内容不会作为有效记录交付。
    always @(posedge sys_clk) begin
        if (put && rst_n) begin
            memory[write_addr] <= push_data;
        end
    end
    always @(posedge sys_clk or negedge rst_n) begin
        if (!rst_n) begin
            write_addr <= 0;
            read_addr  <= 0;
            count      <= 0;
            peak       <= 0;
            dropped    <= 0;
        end else begin
            if (put) begin
                write_addr <= write_addr + 1'b1;
            end else if (push) begin
                dropped <= dropped + 1'b1;
            end
            if (take) begin
                read_addr <= read_addr + 1'b1;
            end
            case ({put, take})
                2'b10: begin
                    count <= count + 1'b1;
                    if (count + 1'b1 > peak) begin
                        peak <= count + 1'b1;
                    end
                end
                2'b01: count <= count - 1'b1;
                default: count <= count;
            endcase
        end
    end
endmodule
