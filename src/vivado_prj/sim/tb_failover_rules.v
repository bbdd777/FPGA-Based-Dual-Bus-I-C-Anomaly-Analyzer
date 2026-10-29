`timescale 1ns / 1ps

module tb_failover_rules;
    reg clk=0;
    always #10 clk=!clk;
    reg rst_n=0;
    reg [63:0] now_tick=0, atick=0, btick=0, stop_tick=0;
    reg fault=0, ack=0, bdone=0, full=0;
    wire waiting, cv, rv, trigger;
    wire [639:0] cp,rp;
    wire [31:0] ignored;
    failover_rules #(.WINDOW_TICKS(10),
                .READ_TICKS              (20)) dut (
        .sys_clk                 (clk),
                .rst_n                   (rst_n),
                .processed_tick          (now_tick),
                .a_fault                 (fault),
                .fault_kind              (8'd1),
        .a_tick                  (atick),
                .b_ack                   (ack),
                .b_tick                  (btick),
                .b_done                  (bdone),
                .b_full                  (full),
                .b_stop_tick             (stop_tick),
        .waiting                 (waiting),
                .correlation_valid       (cv),
                .correlation_tick        (),
                .correlation_payload     (cp),
        .read_valid              (rv),
                .read_tick               (),
                .read_payload            (rp),
                .trigger_valid           (trigger),
        .trigger_reason          (),
                .trigger_link            (),
                .ignored_faults          (ignored)
    );
    task step;
        input [63:0] t;
        input f,a,d,g;
        begin
            @(negedge clk); now_tick=t; fault=f; ack=a; bdone=d; full=g;
            atick=t; btick=t; stop_tick=t;
            @(posedge clk); #1;
        end
    endtask
    initial begin
        #50; @(negedge clk); rst_n=1;
        step(100,1,0,0,0); if (!waiting || cv) $fatal(1,"fault starts only");
        step(105,1,0,0,0); if (ignored!=1) $fatal(1,"duplicate");
        step(110,0,1,0,0); if (!cv || cp[39:32]!=1 || cp[223:192]!=10 || !trigger) $fatal(1,"inclusive ACK boundary");
        step(130,0,0,1,1); if (!rv || rp[39:32]!=1) $fatal(1,"full read boundary");
        step(200,1,1,0,0); if (!cv || cp[223:192]!=0) $fatal(1,"same batch");
        step(201,0,0,1,0); if (!rv || rp[39:32]!=2) $fatal(1,"address ACK not full read");
        step(300,1,0,0,0);
        step(310,0,0,0,0); if(cv) $fatal(1,"must wait through equality");
        step(311,0,1,0,0); if(!cv || cp[39:32]!=2) $fatal(1,"late ACK timeout");
        step(400,1,1,0,0);
        step(422,0,0,0,0); if(!rv || rp[39:32]!=3) $fatal(1,"read missing timeout");
        // 超过32位后的源编号仍正确。
        step(64'h100000010,1,0,0,0);
        step(64'h100000011,0,1,0,0); if(!cv || cp[223:192]!=1) $fatal(1,"64bit tick");
        @(negedge clk); rst_n=0;
        @(negedge clk); rst_n=1;
        #1; if(waiting) $fatal(1,"reset wait");
        $display("PASS ALL tb_failover_rules"); $finish;
    end
endmodule
