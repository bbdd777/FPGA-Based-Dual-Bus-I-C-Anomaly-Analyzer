`timescale 1ns / 1ps

// 功能：按 8N1 发送一个字节；开始时锁存数据，忙期间忽略新请求。
// 时钟：默认 50 MHz，正式默认 1M 波特率，所有逻辑用同一时钟。
// 复位：低有效异步复位，由板级顶层同步释放；复位时 TX 回到空闲高。
// 握手：空闲时 pi_flag=1 的沿接受一个字节；tx_done 在整个停止位发完后高一拍。
module uart_tx #(
    parameter integer UART_BPS = 1_000_000,       // 每秒串行位数，正式目标，50MHz下整除50
    parameter integer CLK_FREQ = 50_000_000   // 系统时钟频率，单位 Hz
) (
    input  wire       sys_clk,               // 系统时钟，上升沿工作
    input  wire       sys_rst_n,             // 低有效复位，顶层同步释放
    input  wire [7:0] pi_data,               // 本次要发送的字节，只在接受沿锁存
    input  wire       pi_flag,               // 一拍发送请求，仅空闲时有效

    output reg        tx,                    // 串行输出，空闲和停止位为 1
    output reg        tx_done,               // 完整字节发送结束，高有效一系统拍
    output reg        tx_busy                // 为 1 时正在发送，不接受下一请求
);

    // ---------------- 参数与内部信号 ----------------
    // BAUD_CNT_MAX 是每位经过的时钟数量；计数 0～N-1，恰好 N 拍。
    // 50 MHz / 115200 向下取整为 434 拍，每位 8680 ns，实际约 115207 baud。
    // 16 位计数支持 2～65536 拍；当前 9600/115200 两种参数都在范围内。
    localparam integer BAUD_CNT_MAX = CLK_FREQ / UART_BPS;

    reg  [15:0] baud_cnt;                    // 当前位已经经过的系统时钟数
    reg  [3:0]  bit_cnt;                     // 当前位：0 起始，1～8 数据，9 停止
    reg  [7:0]  data_reg;                    // 接受请求时保存的完整字节
    wire        byte_accept;                 // 当前沿接受一个新字节
    wire        bit_end;                     // 当前沿完成一个完整位时间

    assign byte_accept = sys_rst_n && !tx_busy && pi_flag;
    assign bit_end     = tx_busy && (baud_cnt == BAUD_CNT_MAX - 1);

    // ---------------- 主逻辑：发送数据锁存 ----------------
    // data_reg：接受请求时更新，其余时间保持；上游可在接受后改变 pi_data。
    always @(posedge sys_clk or negedge sys_rst_n) begin
        if (!sys_rst_n) begin
            data_reg <= 8'd0;
        end else if (byte_accept) begin
            data_reg <= pi_data;
        end
    end

    // ---------------- 主逻辑：位时间计数 ----------------
    // baud_cnt：空闲或每位结束时清零，否则加一；不产生新的分频时钟。
    always @(posedge sys_clk or negedge sys_rst_n) begin
        if (!sys_rst_n) begin
            baud_cnt <= 16'd0;
        end else if (!tx_busy || bit_end) begin
            baud_cnt <= 16'd0;
        end else begin
            baud_cnt <= baud_cnt + 16'd1;
        end
    end

    // ---------------- 主逻辑：当前位索引 ----------------
    // bit_cnt：发送请求接受后从起始位开始；整个位时间结束才推进。
    always @(posedge sys_clk or negedge sys_rst_n) begin
        if (!sys_rst_n) begin
            bit_cnt <= 4'd0;
        end else if (byte_accept) begin
            bit_cnt <= 4'd0;
        end else if (bit_end) begin
            if (bit_cnt == 4'd9) begin
                bit_cnt <= 4'd0;
            end else begin
                bit_cnt <= bit_cnt + 4'd1;
            end
        end
    end

    // ---------------- 主逻辑：输出、忙碌和完成事件 ----------------
    // TX 与 bit_cnt 在同一个沿读取旧索引：结束第0位后，输出 data_reg[0]。
    // 第8位结束才开始停止位；第9位又经过完整 N 拍后才给 tx_done。
    // 忙时不处理 pi_flag；请求不得提前保持到空闲，应由上游发一拍事件。
    always @(posedge sys_clk or negedge sys_rst_n) begin
        if (!sys_rst_n) begin
            tx      <= 1'b1;
            tx_busy <= 1'b0;
            tx_done <= 1'b0;
        end else begin
            tx_done <= 1'b0; // 默认清零，完成事件只保持一系统拍
            if (byte_accept) begin
                tx      <= 1'b0; // 当前沿开始起始位，并保持整个位时间
                tx_busy <= 1'b1;
            end else if (bit_end) begin
                if (bit_cnt == 4'd9) begin
                    tx      <= 1'b1;
                    tx_busy <= 1'b0;
                    tx_done <= 1'b1;
                end else begin
                    case (bit_cnt)
                        4'd0: tx <= data_reg[0];
                        4'd1: tx <= data_reg[1];
                        4'd2: tx <= data_reg[2];
                        4'd3: tx <= data_reg[3];
                        4'd4: tx <= data_reg[4];
                        4'd5: tx <= data_reg[5];
                        4'd6: tx <= data_reg[6];
                        4'd7: tx <= data_reg[7];
                        default: tx <= 1'b1; // 第8位结束，开始停止位
                    endcase
                end
            end
            // 其余时钟沿保持 TX 和忙碌状态，避免一位内重复切换。
        end
    end
endmodule

