`timescale 1ns / 1ps

// 冻结波形分块上传，同时在块间公平插入实时记录。最多连续2条事件后让波形一块。
// 每块最多256样点/128字节：较早样点放低半字节；奇数末点高半字节填0。
// 全波形CRC32针对解包后的样点字节(高四位0)，并不针对压缩字节。
module wave_stream #(
    parameter integer ADDR_WIDTH = 18
) (
    input  wire          sys_clk,
    input  wire          rst_n,
    input  wire          frozen,
    input  wire [31:0]   capture_id,
    input  wire [31:0]   sample_count,
    input  wire [31:0]   trigger_index,
    input  wire [63:0]   trigger_tick,
    input  wire [63:0]   first_tick,
    input  wire [7:0]    reason,
    input  wire [31:0]   correlation_id,
    output reg           upload_done,
    output reg           read_en,
    output wire [ADDR_WIDTH-1:0] read_offset,
    input  wire          read_valid,
    input  wire [3:0]    read_data,
    input  wire          event_valid,
    input  wire [711:0]  event_record,
    output wire          event_pop,
    output reg           frame_valid,
    input  wire          frame_ready,
    input  wire          frame_done,
    output reg  [7:0]    frame_kind,
    output reg  [63:0]   frame_tick,
    output reg  [31:0]   frame_capture,
    output reg  [15:0]   frame_length,
    output reg  [1087:0] frame_payload
);
    localparam [3:0] IDLE = 0, REQUEST = 1, WAIT_READ = 2,
                     OFFER = 3, WAIT_FRAME = 4;
    localparam [1:0] BEGIN_WAVE = 0, CHUNKS = 1, END_WAVE = 2;
    reg [3:0] state;
    reg active;
    reg [1:0] wave_phase;
    reg [1:0] event_burst;
    reg [31:0] offset;
    reg [8:0] chunk_count;
    reg [8:0] chunk_index;
    reg [1023:0] chunk_data;
    reg [31:0] wave_crc;
    reg is_wave;
    wire choose_event = event_valid && (!active || event_burst < 2);

    assign event_pop = state == IDLE && choose_event;
    assign read_offset = offset + chunk_index;

    function [31:0] crc32_sample;
        input [31:0] old_crc;
        input [3:0] value;
        reg [31:0] work;
        integer bit_index;
        begin
            work = old_crc ^ {28'd0, value};
            for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1) begin
                work = work[0] ? (work >> 1) ^ 32'hedb88320 : work >> 1;
            end
            crc32_sample = work;
        end
    endfunction

    // read_en为一拍请求，下一拍等待BRAM的read_valid，不能同沿拿旧read_data。
    // frame_payload在OFFER前完全建立，并保持到frame_tx锁存。
    // 读地址offset、chunk_index及read_en使用同步复位，保护BRAM控制入口。
    always @(posedge sys_clk) begin
        if (!rst_n) begin
            state         <= IDLE;
            active        <= 0;
            wave_phase    <= BEGIN_WAVE;
            event_burst   <= 0;
            offset        <= 0;
            chunk_count   <= 0;
            chunk_index   <= 0;
            chunk_data    <= 0;
            wave_crc      <= 32'hffffffff;
            is_wave       <= 0;
            upload_done   <= 0;
            read_en       <= 0;
            frame_valid   <= 0;
            frame_kind    <= 0;
            frame_tick    <= 0;
            frame_capture <= 0;
            frame_length  <= 0;
            frame_payload <= 0;
        end else begin
            read_en     <= 0;
            upload_done <= 0;
            case (state)
                IDLE: begin
                    if (frozen && !active && !upload_done) begin
                        active      <= 1;
                        wave_phase  <= BEGIN_WAVE;
                        offset      <= 0;
                        wave_crc    <= 32'hffffffff;
                    end
                    if (choose_event) begin
                        frame_kind    <= event_record[711:704];
                        frame_tick    <= event_record[703:640];
                        frame_capture <= 0;
                        frame_length  <= 80;
                        frame_payload <= {448'd0, event_record[639:0]};
                        is_wave       <= 0;
                        event_burst   <= event_burst + 1'b1;
                        state         <= OFFER;
                    end else if (active) begin
                        is_wave       <= 1;
                        event_burst   <= 0;
                        frame_tick    <= trigger_tick;
                        frame_capture <= capture_id;
                        frame_payload <= 0;
                        if (wave_phase == BEGIN_WAVE) begin
                            frame_kind    <= 8'h40;
                            frame_length  <= 48;
                            frame_payload[31:0]    <= 32'd20;
                            frame_payload[63:32]   <= sample_count;
                            frame_payload[95:64]   <= trigger_index;
                            frame_payload[103:96]  <= reason;
                            frame_payload[111:104] <= 8'he4; // 四路依次为A SCL/SDA B SCL/SDA
                            frame_payload[119:112] <= 8'd1;  // nibble编码
                            frame_payload[191:128] <= trigger_tick;
                            frame_payload[255:192] <= first_tick;
                            frame_payload[287:256] <= correlation_id;
                            frame_payload[319:288] <= 32'd1; // 固定配置编号
                            frame_payload[351:320] <= (1 << ADDR_WIDTH);
                            frame_payload[383:352] <= (sample_count < (1 << ADDR_WIDTH)) ? 1 : 0;
                            state <= OFFER;
                        end else if (wave_phase == CHUNKS) begin
                            chunk_count <= (sample_count - offset >= 256) ? 256 : sample_count - offset;
                            chunk_index <= 0;
                            chunk_data  <= 0;
                            state       <= REQUEST;
                        end else begin
                            frame_kind    <= 8'h42;
                            frame_length  <= 16;
                            frame_payload[31:0]  <= sample_count;
                            frame_payload[63:32] <= (sample_count + 1) >> 1;
                            frame_payload[95:64] <= wave_crc ^ 32'hffffffff;
                            frame_payload[103:96] <= reason;
                            state <= OFFER;
                        end
                    end
                end
                REQUEST: begin
                    read_en <= 1;
                    state <= WAIT_READ;
                end
                WAIT_READ: begin
                    if (read_valid) begin
                        chunk_data[chunk_index*4 +: 4] <= read_data;
                        wave_crc <= crc32_sample(wave_crc, read_data);
                        if (chunk_index + 1 == chunk_count) begin
                            // 最后样点尚未进入chunk_data，显式写入payload对应位置。
                            frame_kind <= 8'h41;
                            frame_length <= 8 + ((chunk_count + 1) >> 1);
                            frame_payload <= {chunk_data, 64'd0};
                            frame_payload[chunk_index*4 + 64 +: 4] <= read_data;
                            frame_payload[31:0]  <= offset;
                            frame_payload[47:32] <= {7'd0, chunk_count};
                            frame_payload[55:48] <= 8'd1;
                            state <= OFFER;
                        end else begin
                            chunk_index <= chunk_index + 1'b1;
                            state <= REQUEST;
                        end
                    end
                end
                OFFER: begin
                    frame_valid <= 1;
                    if (frame_valid && frame_ready) begin
                        frame_valid <= 0;
                        state <= WAIT_FRAME;
                    end
                end
                WAIT_FRAME: begin
                    if (frame_done) begin
                        if (is_wave) begin
                            if (wave_phase == BEGIN_WAVE) begin
                                wave_phase <= CHUNKS;
                            end else if (wave_phase == CHUNKS) begin
                                offset <= offset + chunk_count;
                                if (offset + chunk_count == sample_count) begin
                                    wave_phase <= END_WAVE;
                                end
                            end else begin
                                upload_done <= 1;
                                active <= 0;
                            end
                        end
                        state <= IDLE;
                    end
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
