`timescale 1ns / 1ps

// 小缓存提前触发形成131点奇数窗口，物理TX逐位解码，覆盖末半字节和停顿握手。
module tb_stream_1m;
    reg clk=0;
    always #10 clk=!clk;
    reg rst_n=0, trigger=0;
    reg [63:0] tick=0;
    reg [7:0] throttle=0;
    wire frozen,done,ren,rvalid,fv,fr,fd,bv,busy,tx;
    wire [7:0] roffset,bdata,kind;
    wire [3:0] rdata;
    wire [31:0] id,count,index,link,fcap;
    wire [63:0] trig,first,ftick;
    wire [7:0] reason;
    wire [15:0] length;
    wire [1087:0] payload;
    wire can_send = !busy && throttle[2:0]!=3'b111;
    integer hexfile, serialfile, serial_count=0, handshake_count=0;
    reg [7:0] decoded;
    integer bit_index;
    always @(posedge clk) begin
        if (rst_n) begin
            tick<=tick+1'b1;
            throttle<=throttle+1'b1;
            if(bv && can_send) begin
                $fdisplay(hexfile,"%02x",bdata);
                handshake_count=handshake_count+1;
            end
        end
    end
    always @(negedge tx) begin
        if(rst_n) begin
            #1500;
            for(bit_index=0;bit_index<8;bit_index=bit_index+1) begin
                decoded[bit_index]=tx;
                #1000;
            end
            if(!tx) $fatal(1,"missing stop bit");
            $fdisplay(serialfile,"%02x",decoded);
            serial_count=serial_count+1;
        end
    end
    capture_ring #(.ADDR_WIDTH(8)) ring_inst (
        .sys_clk                 (clk),
                .rst_n                   (rst_n),
                .sample_tick             (tick),
                .sample_data             (tick[3:0]),
        .trigger_valid           (trigger),
                .trigger_reason          (8'd5),
                .correlation_id          (32'd9),
                .upload_done             (done),
        .read_en                 (ren),
                .read_offset             (roffset),
                .ready                   (),
                .frozen                  (frozen),
                .read_data               (rdata),
        .read_valid              (rvalid),
                .capture_id              (id),
                .sample_count            (count),
                .trigger_index           (index),
        .trigger_tick            (trig),
                .first_tick              (first),
                .reason                  (reason),
                .linked_correlation      (link),
                .missed_triggers         ()
    );
    wave_stream #(.ADDR_WIDTH(8)) stream_inst (
        .sys_clk                 (clk),
                .rst_n                   (rst_n),
                .frozen                  (frozen),
                .capture_id              (id),
                .sample_count            (count),
        .trigger_index           (index),
                .trigger_tick            (trig),
                .first_tick              (first),
                .reason                  (reason),
                .correlation_id          (link),
        .upload_done             (done),
                .read_en                 (ren),
                .read_offset             (roffset),
                .read_valid              (rvalid),
                .read_data               (rdata),
        .event_valid             (1'b0),
                .event_record            (712'd0),
                .event_pop               (),
                .frame_valid             (fv),
                .frame_ready             (fr),
        .frame_done              (fd),
                .frame_kind              (kind),
                .frame_tick              (ftick),
                .frame_capture           (fcap),
                .frame_length            (length),
                .frame_payload           (payload)
    );
    frame_tx frame_inst (
        .sys_clk                 (clk),
                .rst_n                   (rst_n),
                .frame_valid             (fv),
                .frame_ready             (fr),
                .kind                    (kind),
                .source_tick             (ftick),
        .capture_id              (fcap),
                .payload_length          (length),
                .payload                 (payload),
                .byte_valid              (bv),
                .byte_ready              (can_send),
        .byte_data               (bdata),
                .done                    (fd)
    );
    uart_tx uart_inst (
        .sys_clk                 (clk),
                .sys_rst_n               (rst_n),
                .pi_data                 (bdata),
                .pi_flag                 (bv&&can_send),
                .tx                      (tx),
                .tx_done                 (),
                .tx_busy                 (busy)
    );
    initial begin
        hexfile=$fopen("stream_1m.hex","w");
        serialfile=$fopen("stream_1m_serial.hex","w");
        #100; @(negedge clk); rst_n=1;
        repeat(3) @(negedge clk); trigger=1;
        @(negedge clk); trigger=0;
        wait(done); #1;
        if(count!=131 || serial_count!=handshake_count) $fatal(1,"odd count or physical UART bytes");
        $fclose(hexfile); $fclose(serialfile);
        $display("PASS ALL tb_stream_1m bytes=%0d",serial_count); $finish;
    end
    initial begin #10000000; $fatal(1,"watchdog"); end
endmodule
