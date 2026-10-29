`timescale 1ns / 1ps

// 功能：将两根外部I2C线同步到50MHz域，波形缓存和协议解析共用第二级。
// 只输入，不含三态输出或上拉；电平兼容必须由实际接线保证。
module i2c_input_sync (
    input  wire sys_clk,
    input  wire rst_n,           // 异步置位、顶层同步释放
    input  wire scl_in,          // 外部SCL
    input  wire sda_in,          // 外部SDA

    output wire scl_sync,
    output wire sda_sync
);
    (* ASYNC_REG = "TRUE" *) reg [1:0] scl_pipe;
    (* ASYNC_REG = "TRUE" *) reg [1:0] sda_pipe;

    always @(posedge sys_clk or negedge rst_n) begin
        if (!rst_n) begin
            scl_pipe <= 2'b11;
            sda_pipe <= 2'b11;
        end else begin
            scl_pipe <= {scl_pipe[0], scl_in};
            sda_pipe <= {sda_pipe[0], sda_in};
        end
    end
    assign scl_sync = scl_pipe[1];
    assign sda_sync = sda_pipe[1];
endmodule
