`timescale 1ns / 1ps

// 04版帧：AA55/version/kind/seq32/tick64/capture32/len16/payload/CRC16。
// 小端整数；CRC16-CCITT-FALSE覆盖version至payload，初值FFFF，低字节先发。
// frame_valid && frame_ready接受并锁存完整元数据，忙期间生产者可改变输入。
// byte_valid && byte_ready才推进，故UART忙不会丢字节。done等到最后停止位结束。
module frame_tx (
    input  wire          sys_clk,
    input  wire          rst_n,
    input  wire          frame_valid,
    output wire          frame_ready,
    input  wire [7:0]    kind,
    input  wire [63:0]   source_tick,
    input  wire [31:0]   capture_id,
    input  wire [15:0]   payload_length,
    input  wire [1087:0] payload,
    output wire          byte_valid,
    input  wire          byte_ready,
    output reg  [7:0]    byte_data,
    output reg           done
);
    localparam [1:0] IDLE = 0, SEND = 1, DRAIN = 2;
    reg [1:0] state;
    reg [31:0] next_sequence;
    reg [31:0] sequence_reg;
    reg [7:0] kind_reg;
    reg [63:0] tick_reg;
    reg [31:0] capture_reg;
    reg [15:0] length_reg;
    reg [1087:0] payload_reg;
    reg [15:0] byte_index;
    reg [15:0] crc;

    function [15:0] crc16_byte;
        input [15:0] old_crc;
        input [7:0] value;
        reg [15:0] work;
        integer bit_index;
        begin
            work = old_crc ^ {value, 8'd0};
            for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1) begin
                work = work[15] ? (work << 1) ^ 16'h1021 : work << 1;
            end
            crc16_byte = work;
        end
    endfunction
    assign frame_ready = (state == IDLE);
    assign byte_valid = (state == SEND);

    // 字节索引只在握手沿递增；整个UART字节期间输出保持不变。
    always @(*) begin
        byte_data = 0;
        if (byte_index == 0) begin
            byte_data = 8'haa;
        end else if (byte_index == 1) begin
            byte_data = 8'h55;
        end else if (byte_index == 2) begin
            byte_data = 8'h04;
        end else if (byte_index == 3) begin
            byte_data = kind_reg;
        end else if (byte_index < 8) begin
            byte_data = sequence_reg >> ((byte_index - 4) * 8);
        end else if (byte_index < 16) begin
            byte_data = tick_reg >> ((byte_index - 8) * 8);
        end else if (byte_index < 20) begin
            byte_data = capture_reg >> ((byte_index - 16) * 8);
        end else if (byte_index < 22) begin
            byte_data = length_reg >> ((byte_index - 20) * 8);
        end else if (byte_index < 22 + length_reg) begin
            byte_data = payload_reg >> ((byte_index - 22) * 8);
        end else if (byte_index == 22 + length_reg) begin
            byte_data = crc[7:0];
        end else begin
            byte_data = crc[15:8];
        end
    end
    always @(posedge sys_clk or negedge rst_n) begin
        if (!rst_n) begin
            state         <= IDLE;
            next_sequence <= 0;
            sequence_reg  <= 0;
            kind_reg      <= 0;
            tick_reg      <= 0;
            capture_reg   <= 0;
            length_reg    <= 0;
            payload_reg   <= 0;
            byte_index    <= 0;
            crc           <= 16'hffff;
            done          <= 0;
        end else begin
            done <= 0;
            case (state)
                IDLE: begin
                    if (frame_valid) begin
                        kind_reg      <= kind;
                        tick_reg      <= source_tick;
                        capture_reg   <= capture_id;
                        length_reg    <= payload_length;
                        payload_reg   <= payload;
                        sequence_reg  <= next_sequence;
                        next_sequence <= next_sequence + 1'b1;
                        byte_index    <= 0;
                        crc           <= 16'hffff;
                        state         <= SEND;
                    end
                end
                SEND: begin
                    if (byte_ready) begin
                        if (byte_index >= 2 && byte_index < 22 + length_reg) begin
                            crc <= crc16_byte(crc, byte_data);
                        end
                        if (byte_index == 23 + length_reg) begin
                            state <= DRAIN;
                        end else begin
                            byte_index <= byte_index + 1'b1;
                        end
                    end
                end
                DRAIN: begin
                    if (byte_ready) begin
                        done <= 1;
                        state <= IDLE;
                    end
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
