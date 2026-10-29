`timescale 1ns / 1ps

// 队列满、满时同时出入队、逐条顺序、低阈值N-1/N及恢复、复位。
module tb_pressure;
    reg clk=0;
    always #10 clk=!clk;
    reg rst_n=0, push=0,pop=0,scl=1;
    reg [15:0] value=0;
    reg [63:0] tick=0;
    wire valid,low_valid;
    wire [15:0] head;
    wire [31:0] dropped;
    wire [5:0] peak;
    wire [63:0] low_tick;
    integer item;
    record_fifo #(.WIDTH(16)) fifo_inst (
        .sys_clk                 (clk),
                .rst_n                   (rst_n),
                .push                    (push),
                .push_data               (value),
                .pop                     (pop),
        .valid                   (valid),
                .head                    (head),
                .dropped                 (dropped),
                .peak                    (peak)
    );
    line_low_watch #(.LOW_LIMIT(5)) low_inst (
        .sys_clk                 (clk),
                .rst_n                   (rst_n),
                .scl                     (scl),
                .sample_tick             (tick),
                .valid                   (low_valid),
                .event_tick              (low_tick)
    );
    always @(posedge clk) if(rst_n) tick<=tick+1'b1;
    initial begin
        #100; @(negedge clk); rst_n=1; push=1;
        for(item=0;item<35;item=item+1) begin
            value=item; @(negedge clk);
        end
        push=0;
        if(dropped!=3 || peak!=32 || head!=0) $fatal(1,"queue pressure");
        push=1; pop=1; value=99; @(negedge clk); push=0;
        if(dropped!=3 || head!=1) $fatal(1,"full simultaneous put/take");
        for(item=1;item<32;item=item+1) begin
            if(head!==item) $fatal(1,"queue ordering");
            @(negedge clk);
        end
        if(head!=99) $fatal(1,"replacement tail");
        @(negedge clk); pop=0;
        if(valid) $fatal(1,"queue empty");
        scl=0; repeat(4) @(negedge clk);
        if(low_valid) $fatal(1,"N-1 low");
        @(negedge clk); if(!low_valid || low_tick!=tick-1) $fatal(1,"Nth low source tick");
        @(negedge clk); if(low_valid) $fatal(1,"one pulse per low span");
        repeat(8) @(negedge clk);
        if(low_valid) $fatal(1,"held low duplicate");
        scl=1; @(negedge clk); scl=0; repeat(5) @(negedge clk);
        if(!low_valid) $fatal(1,"recovery enables second fault");
        rst_n=0; @(negedge clk); rst_n=1; #1;
        if(dropped || valid || low_valid) $fatal(1,"reset pressure");
        $display("PASS ALL tb_pressure"); $finish;
    end
endmodule
