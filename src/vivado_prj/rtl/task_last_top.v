`timescale 1ns / 1ps

// 板级顶层：异步复位、同步释放。四根总线引脚始终是输入，无驱动和ACK。
// 无人工布防按键，无串口命令依赖；上电后自动监测、抓拍和上传。
module task_last_top #(
    parameter integer UART_BPS = 1_000_000
) (
    input  wire       sys_clk,
    input  wire       sys_rst_n,
    input  wire       scl_a_in,
    input  wire       sda_a_in,
    input  wire       scl_b_in,
    input  wire       sda_b_in,
    output wire       tx,
    output wire [3:0] led
);
    (* ASYNC_REG = "TRUE" *) reg [1:0] reset_pipe;
    always @(posedge sys_clk or negedge sys_rst_n) begin
        if (!sys_rst_n) begin
            reset_pipe <= 0;
        end else begin
            reset_pipe <= {reset_pipe[0],1'b1};
        end
    end
    analyzer_core #(.UART_BPS(UART_BPS)) core_inst (
        .sys_clk                 (sys_clk),
                .rst_n                   (reset_pipe[1]),
                .scl_a_in                (scl_a_in),
                .sda_a_in                (sda_a_in),
        .scl_b_in                (scl_b_in),
                .sda_b_in                (sda_b_in),
                .tx                      (tx),
                .led                     (led),
        .debug_byte_valid        (),
                .debug_byte_data         ()
    );
endmodule
