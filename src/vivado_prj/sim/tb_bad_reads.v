`timescale 1ns / 1ps

// 位级反例：错误指针、13字节、读地址NACK、中途数据NACK、无STOP。
module tb_bad_reads;
    reg clk=0;
    always #10 clk=!clk;
    reg rst_n=0;
    reg [1:0] scl=2'b11, sda=2'b11;
    wire tx, byte_valid;
    wire [7:0] byte_data;
    wire [3:0] led;
    integer mode;
    integer fd, capture_total=0, corr_total=0, read_total=0;
    integer full_total=0, nack_total=0, low_total=0;
    analyzer_core #(.ADDR_WIDTH(8), .UART_BPS(50_000_000),
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
            if (dut.result_payload[39:32]!=2 && dut.result_payload[39:32]!=3) $fatal(1,"invalid read was accepted");
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
    task bad_read_b;
        input integer failure;
        integer byte_index;
        begin
            start_bus(1); byte_bus(1,8'hd0,0);
            byte_bus(1,failure==0 ? 8'h00 : 8'h3b,0);
            start_bus(1); byte_bus(1,8'hd1,failure==2);
            if(failure!=2) begin
                for(byte_index=0;byte_index<(failure==1 ? 13 : 14);byte_index=byte_index+1)
                    byte_bus(1,8'h20+byte_index,(byte_index==(failure==1 ? 12 : 13)) || (failure==3 && byte_index==6));
            end
            stop_bus(1);
        end
    endtask
    initial begin
        fd=$fopen("bad_reads_stream.hex","w");
        #100; @(negedge clk); rst_n=1;
        cycles(1000);
        for(mode=0;mode<4;mode=mode+1) begin
            start_bus(0); byte_bus(0,8'hd4,1); stop_bus(0);
            bad_read_b(mode); cycles(1000);
            if(corr_total!=mode+1 || read_total!=mode+1 || full_total!=0)
                $fatal(1,"bad read mode=%0d corr=%0d read=%0d",mode,corr_total,read_total);
        end
        // B仅首地址ACK，后续一直无STOP，必须在2ms读窗口之后发布读取超时。
        start_bus(0); byte_bus(0,8'hd4,1); stop_bus(0);
        start_bus(1); byte_bus(1,8'hd0,0); cycles(105000);
        if(corr_total!=5 || read_total!=5 || dut.waiting) $fatal(1,"missing STOP read timeout");
        stop_bus(1); cycles(100000);
        $fclose(fd);
        $display("PASS ALL tb_bad_reads rejected=4 read_timeout=1"); $finish;
    end
    initial begin #500000000; $fatal(1,"watchdog"); end
endmodule
