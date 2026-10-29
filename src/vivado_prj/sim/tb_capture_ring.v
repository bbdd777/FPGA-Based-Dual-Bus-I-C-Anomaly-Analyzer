`timescale 1ns / 1ps

// 正式18位深度逐点核对，不以256点代替最终深度测试。
module tb_capture_ring;
    reg sys_clk = 0;
    always #10 sys_clk = !sys_clk;
    reg rst_n = 0;
    reg [63:0] tick = 0;
    reg trigger = 0;
    reg done = 0;
    reg read_en = 0;
    reg [17:0] offset = 0;
    wire ready, frozen, valid;
    wire [3:0] data;
    wire [31:0] count, index, cap, missed;
    wire [63:0] first, triggered;
    integer point;
    capture_ring dut (
        .sys_clk                 (sys_clk),
                .rst_n                   (rst_n),
                .sample_tick             (tick),
                .sample_data             (tick[3:0]),
        .trigger_valid           (trigger),
                .trigger_reason          (8'd5),
                .correlation_id          (32'd7),
        .upload_done             (done),
                .read_en                 (read_en),
                .read_offset             (offset),
                .ready                   (ready),
        .frozen                  (frozen),
                .read_data               (data),
                .read_valid              (valid),
                .capture_id              (cap),
        .sample_count            (count),
                .trigger_index           (index),
                .trigger_tick            (triggered),
        .first_tick              (first),
                .reason                  (),
                .linked_correlation      (),
                .missed_triggers         (missed)
    );
    always @(posedge sys_clk) begin
        if (rst_n) tick <= tick + 1'b1;
    end
    task fire;
        begin
            @(negedge sys_clk); trigger = 1;
            @(negedge sys_clk); trigger = 0;
        end
    endtask
    task read_all;
        begin
            for (point=0; point<count; point=point+1) begin
                @(negedge sys_clk); offset = point; read_en = 1;
                @(posedge sys_clk); #1;
                if (!valid || data !== ((first+point) & 15)) $fatal(1,"RAM order at %0d",point);
            end
            @(negedge sys_clk); read_en = 0;
        end
    endtask
    initial begin
        #100; @(negedge sys_clk); rst_n = 1;
        repeat (300000) @(negedge sys_clk); // 地址先绕回，证明读出不是物理地址顺序
        fire();
        wait(frozen); #1;
        if (count != 262144 || index != 131072 || triggered-first != index) $fatal(1,"full depth metadata");
        read_all();
        fire();
        if (missed != 1) $fatal(1,"busy capture must be counted");
        @(negedge sys_clk); done = 1;
        @(negedge sys_clk); done = 0;
        repeat(7) @(negedge sys_clk);
        fire();
        wait(frozen); #1;
        if (count >= 262144 || index >= 20 || count != index+131072) $fatal(1,"short history");
        read_all();
        // 冻结中复位后立即恢复自动滚动，旧数据不能作为新历史。
        @(negedge sys_clk); rst_n = 0;
        @(negedge sys_clk); rst_n = 1;
        #1; if (!ready || frozen) $fatal(1,"reset capture");
        $display("PASS ALL tb_capture_ring"); $finish;
    end
    initial begin #50000000; $fatal(1,"watchdog"); end
endmodule
