`timescale 1ns / 1ps

// 自动滚动的四位环形缓存：每个50MHz时钟保存一个同步样点。
// 完整窗口：严格在触发前的DEPTH/2点，触发点，之后DEPTH/2-1点。
// 触发点属于后半段。上电历史不足时缩短输出，绝不补造历史。
// 冻结后只读；收到整个上传结束事件才自动恢复滚动，无人工布防输入。
module capture_ring #(
    parameter integer ADDR_WIDTH = 18
) (
    input  wire                    sys_clk,
    input  wire                    rst_n,
    input  wire [63:0]             sample_tick,
    input  wire [3:0]              sample_data,
    input  wire                    trigger_valid,
    input  wire [7:0]              trigger_reason,
    input  wire [31:0]             correlation_id,
    input  wire                    upload_done,
    input  wire                    read_en,
    input  wire [ADDR_WIDTH-1:0]   read_offset,

    output wire                    ready,
    output wire                    frozen,
    output reg  [3:0]              read_data,
    output reg                     read_valid,
    output reg  [31:0]             capture_id,
    output reg  [31:0]             sample_count,
    output reg  [31:0]             trigger_index,
    output reg  [63:0]             trigger_tick,
    output reg  [63:0]             first_tick,
    output reg  [7:0]              reason,
    output reg  [31:0]             linked_correlation,
    output reg  [31:0]             missed_triggers
);
    localparam integer DEPTH = 1 << ADDR_WIDTH;
    localparam integer HALF = DEPTH / 2;
    localparam [1:0] ROLL = 2'd0, POST = 2'd1, HOLD = 2'd2;
    reg [1:0] state;
    (* ram_style = "block" *) reg [3:0] memory [0:DEPTH-1];
    reg [ADDR_WIDTH-1:0] write_addr;
    reg [ADDR_WIDTH-1:0] first_addr;
    reg [ADDR_WIDTH:0] history_count;
    reg [ADDR_WIDTH:0] post_left;
    wire [ADDR_WIDTH-1:0] physical_read = first_addr + read_offset;

    assign ready = (state == ROLL);
    assign frozen = (state == HOLD);

    // BRAM控制入口仅由同步寄存器驱动。避免异步复位直接改变RAM地址/使能，
    // 消除REQP-1839告警；复位内容无效由history_count保证，不清空整块RAM。

    // BRAM单拍同步读：请求沿之后read_valid/read_data一起有效。
    // 读取时存储器已冻结；不依赖同地址读写的厂商特定返回值。
    always @(posedge sys_clk) begin
        // 复位期间允许写无效内容；有效历史计数清0，解除复位后的首样点照常保存。
        // 不把异步rst_n直接接到BRAM使能，也不丢掉释放复位后的第一个历史样点。
        if (state != HOLD) begin
            memory[write_addr] <= sample_data;
        end
        if (read_en && frozen) begin
            read_data <= memory[physical_read];
        end
    end
    always @(posedge sys_clk) begin
        if (!rst_n) begin
            read_valid <= 1'b0;
        end else begin
            read_valid <= read_en && frozen;
        end
    end

    // state、地址与计数：地址用18位，点数必须能表示262144，不能用18位计数。
    // 公共协议字段统一32位；历史计数只需记到HALF，避免复杂的全深度比较。
    always @(posedge sys_clk) begin
        if (!rst_n) begin
            state              <= ROLL;
            write_addr         <= 0;
            first_addr         <= 0;
            history_count      <= 0;
            post_left          <= 0;
            capture_id         <= 0;
            sample_count       <= 0;
            trigger_index      <= 0;
            trigger_tick       <= 0;
            first_tick         <= 0;
            reason             <= 0;
            linked_correlation <= 0;
            missed_triggers    <= 0;
        end else begin
            if (trigger_valid && !ready) begin
                missed_triggers <= missed_triggers + 1'b1;
            end
            case (state)
                ROLL: begin
                    write_addr <= write_addr + 1'b1;
                    if (history_count < HALF) begin
                        history_count <= history_count + 1'b1;
                    end
                    if (trigger_valid) begin
                        // 本沿写入的是触发样点；first_addr按旧的下一写地址计算。
                        first_addr         <= write_addr - history_count;
                        sample_count       <= history_count + HALF;
                        trigger_index      <= history_count;
                        trigger_tick       <= sample_tick;
                        first_tick         <= sample_tick - history_count;
                        reason             <= trigger_reason;
                        linked_correlation <= correlation_id;
                        capture_id         <= capture_id + 1'b1;
                        post_left          <= HALF - 1;
                        state              <= POST;
                    end
                end
                POST: begin
                    write_addr <= write_addr + 1'b1;
                    // 尚需HALF-1点；最后一个写入沿之后才公布frozen。
                    if (post_left == 1) begin
                        state <= HOLD;
                    end else begin
                        post_left <= post_left - 1'b1;
                    end
                end
                HOLD: begin
                    if (upload_done) begin
                        history_count <= 0;
                        state <= ROLL;
                    end
                end
                default: state <= ROLL;
            endcase
        end
    end
endmodule
