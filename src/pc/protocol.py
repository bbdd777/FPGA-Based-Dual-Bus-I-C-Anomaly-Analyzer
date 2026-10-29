"""04版串口协议。此模块只处理字节、校验和样点，不依赖串口或图形库。"""
from dataclasses import dataclass
import struct
import zlib

MAGIC = b"\xaa\x55"
VERSION = 4
HEADER = struct.Struct("<2sBBIQIH")
BEGIN = struct.Struct("<IIIBBBBQQIIII")
MAX_PAYLOAD = 136
MAX_SAMPLES = 262144


def crc16(data: bytes, initial: int = 0xFFFF) -> int:
    crc = initial
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ (0x1021 if crc & 0x8000 else 0)) & 0xFFFF
    return crc


@dataclass(frozen=True)
class Frame:
    kind: int
    sequence: int
    tick: int
    capture_id: int
    payload: bytes


def encode(frame: Frame) -> bytes:
    header = HEADER.pack(MAGIC, VERSION, frame.kind, frame.sequence, frame.tick,
                         frame.capture_id, len(frame.payload))
    body = header + frame.payload
    return body + struct.pack("<H", crc16(body[2:]))


class Parser:
    """按长度吃掉完整帧；负载内AA55不会重启解析。坏CRC后逐字节重新同步。"""
    def __init__(self):
        self.buffer = bytearray()
        self.crc_errors = 0
        self.discarded_bytes = 0
        self.sequence_gaps = 0
        self.resets = 0
        self.last_sequence = None
        self.last_tick = None

    def feed(self, data: bytes) -> list[Frame]:
        self.buffer.extend(data)
        frames = []
        while True:
            start = self.buffer.find(MAGIC)
            if start < 0:
                keep = 1 if self.buffer[-1:] == b"\xaa" else 0
                self.discarded_bytes += len(self.buffer) - keep
                self.buffer[:] = self.buffer[-keep:] if keep else b""
                break
            if start:
                self.discarded_bytes += start
                del self.buffer[:start]
            if len(self.buffer) < HEADER.size:
                break
            _, version, kind, seq, tick, cap_id, length = HEADER.unpack_from(self.buffer)
            if version != VERSION or length > MAX_PAYLOAD:
                self.discarded_bytes += 1
                del self.buffer[0]
                continue
            size = HEADER.size + length + 2
            if len(self.buffer) < size:
                # 合法长度半包等待后续；最大帧只有160字节，不会无限占内存。
                break
            if crc16(self.buffer[2:size-2]) != struct.unpack_from("<H", self.buffer, size-2)[0]:
                self.crc_errors += 1
                del self.buffer[0]
                continue
            frame = Frame(kind, seq, tick, cap_id, bytes(self.buffer[HEADER.size:size-2]))
            # 配置帧seq=0且时钟回退表示FPGA重启；序号本身允许32位自然绕回。
            if (kind == 0x11 and seq == 0 and self.last_sequence is not None
                    and (self.last_tick is None or tick <= self.last_tick)):
                self.resets += 1
                self.last_sequence = None
            if self.last_sequence is not None:
                expected = (self.last_sequence + 1) & 0xFFFFFFFF
                if seq != expected:
                    self.sequence_gaps += (seq - expected) & 0xFFFFFFFF
            self.last_sequence = seq
            self.last_tick = tick
            frames.append(frame)
            del self.buffer[:size]
        return frames


class CaptureError(ValueError):
    pass


@dataclass(frozen=True)
class Capture:
    capture_id: int
    period_ns: int
    trigger_index: int
    reason: int
    trigger_tick: int
    first_tick: int
    correlation_id: int
    config_id: int
    depth: int
    flags: int
    samples: bytes


class Assembler:
    """单RAM上传顺序拼接。错偏移、重复块、坏末包均拒收；不把缺点补成0。"""
    def __init__(self):
        self.pending = None
        self.errors = []
        self.error_count = 0

    def _error(self, message):
        self.error_count += 1
        self.errors.append(message)
        # 长时间在线时保留最近200个说明及累计计数，错误文本不能无界占用内存。
        del self.errors[:-200]

    def reset(self, reason="FPGA重新启动"):
        if self.pending is not None:
            self._error(reason + "，未完成波形已丢弃")
        self.pending = None

    def accept(self, frame: Frame):
        try:
            return self._accept(frame)
        except (CaptureError, struct.error) as error:
            self._error(str(error))
            self.pending = None
            return None

    def _accept(self, frame):
        p = frame.payload
        if frame.kind == 0x40:
            if len(p) != BEGIN.size:
                raise CaptureError("波形开始长度错误")
            period, count, index, reason, mapping, encoding, reserved, tick, first, link, config, depth, flags = BEGIN.unpack(p)
            if not (0 < count <= depth <= MAX_SAMPLES and 0 <= index < count):
                raise CaptureError("点数或触发索引越界")
            if period != 20 or mapping != 0xE4 or encoding != 1 or reserved:
                raise CaptureError("不支持的采样配置或编码")
            if tick != first + index or frame.tick != tick:
                raise CaptureError("触发时基不一致")
            if self.pending is not None:
                self._error("新波形开始前上一波形未完成")
            self.pending = dict(frame=frame, count=count, index=index, period=period,
                                reason=reason, tick=tick, first=first, link=link,
                                config=config, depth=depth, flags=flags, samples=bytearray())
        elif frame.kind in (0x41, 0x42):
            state = self.pending
            if state is None:
                raise CaptureError("没有开始帧的波形片段")
            if frame.capture_id != state["frame"].capture_id or frame.tick != state["tick"]:
                raise CaptureError("波形编号或时基变化")
            if frame.kind == 0x41:
                if len(p) < 8:
                    raise CaptureError("波形块过短")
                offset, count, encoding, reserved = struct.unpack_from("<IHBB", p)
                if offset != len(state["samples"]) or not 1 <= count <= 256:
                    raise CaptureError("波形偏移不连续或块点数错误")
                if encoding != 1 or reserved or len(p) != 8 + (count+1)//2:
                    raise CaptureError("波形块编码或长度错误")
                if offset + count > state["count"]:
                    raise CaptureError("波形块超过总点数")
                if count % 2 and p[-1] & 0xF0:
                    raise CaptureError("奇数末点填充非零")
                decoded = bytearray()
                for value in p[8:]:
                    decoded.extend((value & 15, value >> 4))
                state["samples"].extend(decoded[:count])
            else:
                if len(p) != 16:
                    raise CaptureError("波形结束长度错误")
                count, packed, checksum, reason = struct.unpack_from("<IIIB", p)
                raw = bytes(state["samples"])
                if (count != state["count"] or len(raw) != count or packed != (count+1)//2
                        or reason != state["reason"] or any(p[13:])):
                    raise CaptureError("波形结束计数或原因错误")
                if zlib.crc32(raw) != checksum:
                    raise CaptureError("完整波形CRC32错误")
                self.pending = None
                return Capture(frame.capture_id, state["period"], state["index"], reason,
                               state["tick"], state["first"], state["link"], state["config"],
                               state["depth"], state["flags"], raw)
        return None


def capture_frames(capture: Capture, sequence=0):
    """离线回放/测试使用，与真实RTL完全相同的线上格式。"""
    c = capture
    begin = BEGIN.pack(c.period_ns, len(c.samples), c.trigger_index, c.reason, 0xE4, 1, 0,
                       c.trigger_tick, c.first_tick, c.correlation_id, c.config_id, c.depth, c.flags)
    payloads = [(0x40, begin)]
    for offset in range(0, len(c.samples), 256):
        values = c.samples[offset:offset+256]
        packed = bytes(values[i] | ((values[i+1] if i+1 < len(values) else 0) << 4)
                       for i in range(0, len(values), 2))
        payloads.append((0x41, struct.pack("<IHBB", offset, len(values), 1, 0)+packed))
    payloads.append((0x42, struct.pack("<IIIB3x", len(c.samples), (len(c.samples)+1)//2,
                                     zlib.crc32(c.samples), c.reason)))
    return [Frame(kind, (sequence+i) & 0xFFFFFFFF, c.trigger_tick, c.capture_id, payload)
            for i, (kind, payload) in enumerate(payloads)]
