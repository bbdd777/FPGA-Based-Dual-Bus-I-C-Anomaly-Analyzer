`timescale 1ns / 1ps

// 400kHz真实位级激励；正式262144点缓存。只把UART参数加速为50M供长流仿真。
// 另有tb_uart_1m检查正式1M的每位时间，不能用本加速日志证明实物吞吐。
module tb_analyzer_core;
    reg clk=0;
    always #10 clk=!clk;
    reg rst_n=0;
    reg [1:0] scl=2'b11, sda=2'b11;
    wire tx, byte_valid;
    wire [7:0] byte_data;
    wire [3:0] led;
    integer fd, capture_total=0, corr_total=0, read_total=0;
    integer full_total=0, nack_total=0, low_total=0;
    analyzer_core #(.UART_BPS(50_000_000),
                .STATUS_TICKS            (500000)) dut (
        .sys_clk                 (clk),
                .rst_n                   (rst_n),
                .scl_a_in                (scl[0]),
                .sda_a_in                (sda[0]),
        .scl_b_in                (scl[1]),
                .sda_b_in                (sda[1]),
                .tx                      (tx),
                .led                     (led),
        .debug_byte_valid        (byte_valid),
                .debug_byte_data         (byte_data)
    );
    always @(posedge clk) begin
        if (byte_valid) $fdisplay(fd,"%02x",byte_data);
        if (dut.upload_done) capture_total = capture_total+1;
        if (dut.corr_valid) begin
            corr_total = corr_total+1;
            if (dut.corr_payload[39:32]!=1) $fatal(1,"correlation success expected");
        end
        if (dut.result_valid) begin
            read_total=read_total+1;
            if (dut.result_payload[39:32]!=1) $fatal(1,"full read success expected");
        end
        if (dut.summary_valid[1] && dut.full_read[1]) full_total=full_total+1;
        if (dut.address_fault[0]) nack_total=nack_total+1;
        if (dut.low_valid[0]) low_total=low_total+1;
    end
    task cycles;
        input integer n;
        begin repeat(n) @(negedge clk); end
    endtask
    task start_bus;
        input integer bus;
        begin
            scl[bus]=0; sda[bus]=1; cycles(65);
            scl[bus]=1; cycles(60); sda[bus]=0; cycles(60);
            scl[bus]=0; cycles(65);
        end
    endtask
    task byte_bus;
        input integer bus;
        input [7:0] value;
        input no_ack;
        integer bit_index;
        begin
            for(bit_index=7;bit_index>=0;bit_index=bit_index-1) begin
                sda[bus]=value[bit_index]; cycles(65);
                scl[bus]=1; cycles(60); scl[bus]=0;
            end
            sda[bus]=no_ack; cycles(65); scl[bus]=1; cycles(60); scl[bus]=0;
        end
    endtask
    task stop_bus;
        input integer bus;
        begin
            sda[bus]=0; cycles(65); scl[bus]=1; cycles(60);
            sda[bus]=1; cycles(60);
        end
    endtask
    task read_b;
        integer byte_index;
        begin
            start_bus(1); byte_bus(1,8'hd0,0); byte_bus(1,8'h3b,0);
            start_bus(1); byte_bus(1,8'hd1,0);
            for(byte_index=0;byte_index<14;byte_index=byte_index+1)
                byte_bus(1,8'h20+byte_index,byte_index==13);
            stop_bus(1);
        end
    endtask
    initial begin
        fd=$fopen("core_stream.hex","w");
        #100; @(negedge clk); rst_n=1;
        cycles(150000);
        // M2：A错地址NACK，随后B完整14字节。无任何ARM命令。
        start_bus(0); byte_bus(0,8'hd4,1); stop_bus(0); read_b();
        wait(capture_total==1); cycles(50);
        if(corr_total!=1 || read_total!=1 || nack_total!=1 || full_total!=1) $fatal(1,"M2 results");
        // 后续正常B读取必须产生另一份原始波形，不能覆盖PC端固定的故障证据。
        cycles(150000); read_b(); wait(capture_total==2); cycles(50);
        // M3：A低持续1000us；500us确认后才开始B，两个过程存在于同一捕获。
        cycles(150000); scl[0]=0; cycles(25500); read_b(); cycles(30000); scl[0]=1;
        wait(capture_total==3); cycles(50);
        if(corr_total!=2 || read_total!=2 || low_total!=1 || full_total!=3) $fatal(1,"M3 results");
        if(dut.drops[0] || dut.drops[1] || dut.drops[2] || dut.drops[4]) $fatal(1,"unexpected FIFO loss");
        $fclose(fd);
        $display("PASS ALL tb_analyzer_core captures=%0d full_reads=%0d",capture_total,full_total);
        $finish;
    end
    initial begin #500000000; $fatal(1,"watchdog"); end
endmodule
