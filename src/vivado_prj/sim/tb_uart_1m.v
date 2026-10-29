`timescale 1ns / 1ps
module tb_uart_1m;
    reg clk=0;
    always #10 clk=!clk;
    reg rst_n=0, flag=0;
    reg [7:0] value=8'ha6;
    wire tx,done,busy;
    integer bit_index;
    reg [7:0] received;
    time started;
    uart_tx #(.UART_BPS(1000000)) dut (
        .sys_clk                 (clk),
                .sys_rst_n               (rst_n),
                .pi_data                 (value),
                .pi_flag                 (flag),
        .tx                      (tx),
                .tx_done                 (done),
                .tx_busy                 (busy)
    );
    initial begin
        #100; @(negedge clk); rst_n=1;
        @(negedge clk); flag=1;
        @(negedge tx); started=$time;
        @(negedge clk); flag=0; value=0;
        #1480; // 起始沿到第一个数据位中心共1500ns，已过去20ns。
        for(bit_index=0;bit_index<8;bit_index=bit_index+1) begin
            received[bit_index]=tx; #1000;
        end
        if(!tx || received!=8'ha6) $fatal(1,"UART 8N1 bit decode");
        wait(done); #1;
        if($time-started!=10001) $fatal(1,"UART stop duration %0t",$time-started);
        $display("PASS ALL tb_uart_1m"); $finish;
    end
endmodule
