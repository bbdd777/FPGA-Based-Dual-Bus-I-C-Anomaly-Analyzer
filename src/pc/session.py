"""工作线程持有的会话。故障证据固定，最新B原始波形另存，所有数据先落盘。"""
from collections import deque
from datetime import datetime
from dataclasses import asdict, dataclass
from pathlib import Path
import hashlib
import json
import struct
import time

from protocol import Assembler, Parser, Capture
from waveform import decode_i2c
from faults import capture_fault, update_a_fault
from decoded_panel import sensor_values


def decode_record(frame):
    p = frame.payload
    result = dict(kind=frame.kind, sequence=frame.sequence, tick=frame.tick,
                  capture_id=frame.capture_id)
    if len(p) != 80:
        raise ValueError("实时记录长度必须是80字节")
    if frame.kind in (0x20, 0x21):
        bus, addr, rw, flags, pointer, count = p[:6]
        if count > 32 or bus != frame.kind-0x20:
            raise ValueError("摘要字节数或总线号错误")
        result.update(bus=bus, address=addr, rw=rw, flags=flags, pointer=pointer,
                      count=count, start_tick=struct.unpack_from("<Q", p, 8)[0],
                      stop_tick=struct.unpack_from("<Q", p, 16)[0],
                      data=p[24:24+count].hex(" "), full_read=bool(flags & 2),
                      nack_mask=struct.unpack_from("<I", p, 56)[0])
        # B的温度换算系数和A不同，界面默认只报告有符号原始值，不套用6050公式。
        if flags & 2 and count == 14:
            result["sensor_raw"] = dict(zip(("AX", "AY", "AZ", "TEMP", "GX", "GY", "GZ"),
                                             struct.unpack(">7h", p[24:38])))
    elif frame.kind in (0x30, 0x31):
        result.update(bus=p[0], fault=p[1], address=p[2])
    elif frame.kind == 0x32:
        result.update(correlation_id=struct.unpack_from("<I", p)[0], result=p[4], fault=p[5],
                      start_tick=struct.unpack_from("<Q", p, 8)[0],
                      end_tick=struct.unpack_from("<Q", p, 16)[0],
                      elapsed_ticks=struct.unpack_from("<I", p, 24)[0])
    elif frame.kind == 0x33:
        result.update(correlation_id=struct.unpack_from("<I", p)[0], result=p[4],
                      start_tick=struct.unpack_from("<Q", p, 8)[0],
                      end_tick=struct.unpack_from("<Q", p, 16)[0])
    elif frame.kind == 0x11:
        values = struct.unpack_from("<7I", p)
        result.update(zip(("period_ns", "depth", "baud", "low_ticks", "window_ticks",
                           "read_ticks", "config_id"), values))
    elif frame.kind == 0x10:
        flags, missed, accepted, ignored = struct.unpack_from("<4I", p)
        result.update(ready=bool(flags & 1), frozen=bool(flags & 2), missed_captures=missed,
                      accepted_captures=accepted, ignored_faults=ignored,
                      fifo_drops=list(struct.unpack_from("<7I", p, 16)),
                      fifo_peaks=list(p[44:51]), current_capture=struct.unpack_from("<I", p, 52)[0])
    return result


@dataclass(frozen=True)
class SavedCapture:
    capture: Capture
    path: Path | None
    b_reads: tuple
    session_number: int
    a_fault: dict | None = None


class Session:
    def __init__(self, directory=None, input_mode='import'):
        self.input_mode = input_mode
        self.receipt_order = 0
        self.directory = Path(directory) if directory else None
        if self.directory:
            self.directory.mkdir(parents=True, exist_ok=True)
        self.parser, self.assembler = Parser(), Assembler()
        self.captures = deque(maxlen=32)
        self.records = deque(maxlen=2000)
        self.pinned = None
        # 首份证据继续保留供旧接口使用；界面自动跟随使用另一指针。
        # 只有整份波形通过重组、校验和归档后，才更新最新故障。
        self.latest_fault = None
        self.latest_b = None
        self.latest_summary = {}
        self.latest_sensor_summary = {}
        self.latest_bus_fault = {}
        self.status, self.config = {}, {}
        self.latest_a_fault = None
        self.error = ""
        self.received_bytes = 0
        self.session_number = 0
        self._raw = open(self.directory / "serial.raw.bin", "ab") if self.directory else None
        self._log = open(self.directory / "events.jsonl", "a", encoding="utf-8") if self.directory else None
        self._last_flush = time.monotonic()

    def close(self):
        for stream in (self._raw, self._log):
            if stream:
                stream.flush()
                stream.close()

    def feed(self, data, host_received_at=None):
        # 分片帧使用收到最后一个分片的批次时间；直接导入则明确标注为导入时刻。
        received_at = host_received_at or datetime.now().astimezone().isoformat(timespec='milliseconds')
        self.received_bytes += len(data)
        if self._raw:
            self._raw.write(data)
        for frame in self.parser.feed(data):
            if frame.kind == 0x11 and frame.sequence == 0:
                self.session_number += 1
                self.assembler.reset()
                # 历史故障仍保留；新设备启动后最新状态不能沿用旧读数。
                self.latest_summary.clear()
                self.latest_sensor_summary.clear()
                self.latest_bus_fault.clear()
            if frame.kind < 0x40:
                try:
                    record = decode_record(frame)
                except ValueError as error:
                    self.error = str(error)
                    continue
                record["session_number"] = self.session_number
                self.receipt_order += 1
                record.update(host_received_at=received_at, host_received_order=self.receipt_order,
                              input_mode=self.input_mode)
                self.records.append(record)
                if self._log:
                    self._log.write(json.dumps(record, ensure_ascii=False)+"\n")
                if frame.kind in (0x20, 0x21):
                    self.latest_summary[record["bus"]] = record
                    if sensor_values(record) is not None:
                        self.latest_sensor_summary[record['bus']] = record
                elif frame.kind in (0x30, 0x31):
                    self.latest_bus_fault[record['bus']] = record
                elif frame.kind == 0x10:
                    self.status = record
                elif frame.kind == 0x11:
                    self.config = record
                self.latest_a_fault = update_a_fault(self.latest_a_fault, record, self.config)
                if frame.kind == 0x32:
                    # 分开的FIFO可能使完整读结果先到；关联ID明确后再补上同一结果。
                    previous_read = next((r for r in reversed(self.records) if r['kind'] == 0x33
                                          and r.get('correlation_id') == record['correlation_id']
                                          and r['session_number'] == record['session_number']), None)
                    if previous_read:
                        self.latest_a_fault = update_a_fault(self.latest_a_fault, previous_read, self.config)
            capture = self.assembler.accept(frame)
            if capture:
                self._save(capture)
        if self._log and time.monotonic()-self._last_flush >= 1:
            self._log.flush()
            self._raw.flush()
            self._last_flush = time.monotonic()

    def _save(self, capture):
        # B完整读必须从本次真实样点独立解码得到，不能靠摘要合成理想阶梯图。
        reads = tuple(t for t in decode_i2c(capture.samples, 1) if t.full_read)
        # 在解析/归档线程生成本份原因，界面刷新不反复扫描整段原始波形。
        diagnosis = capture_fault(capture, self.records, self.config, reads, self.session_number)
        path = None
        if self.directory:
            prefix = f"s{self.session_number:03d}_capture_{capture.capture_id:08d}"
            path = self.directory / (prefix+".json")
            raw_path = self.directory / (prefix+".samples.bin")
            raw_path.write_bytes(capture.samples)
            metadata = asdict(capture)
            del metadata["samples"]
            metadata.update(sample_count=len(capture.samples), samples_file=raw_path.name,
                            sha256=hashlib.sha256(capture.samples).hexdigest(),
                            b_full_reads=[asdict(t) | {"data": t.data.hex()} for t in reads],
                            session_number=self.session_number, a_fault=diagnosis)
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(path)
        saved = SavedCapture(capture, path, reads, self.session_number, diagnosis)
        self.captures.append(saved)
        if capture.reason in (4, 5):
            self.latest_fault = saved
            if self.pinned is None:
                self.pinned = saved
        if reads:
            self.latest_b = saved

    def snapshot(self):
        return dict(pinned=self.pinned, latest_fault=self.latest_fault,
                    latest_b=self.latest_b, captures=tuple(self.captures),
                    records=tuple(self.records)[-100:], latest_summary=dict(self.latest_summary),
                    latest_sensor_summary=dict(self.latest_sensor_summary),
                    latest_bus_fault=dict(self.latest_bus_fault),
                    status=dict(self.status), config=dict(self.config), error=self.error,
                    latest_a_fault=dict(self.latest_a_fault) if self.latest_a_fault else None,
                    bytes=self.received_bytes, crc_errors=self.parser.crc_errors,
                    sequence_gaps=self.parser.sequence_gaps, discarded=self.parser.discarded_bytes,
                    assembler_errors=tuple(self.assembler.errors[-10:]),
                    assembler_error_count=self.assembler.error_count,
                    receiving_wave=self.assembler.pending is not None,
                    wave_points=(len(self.assembler.pending["samples"]) if self.assembler.pending else 0))


def load_capture(path):
    path = Path(path)
    metadata = json.loads(path.read_text(encoding="utf-8"))
    raw_path = (path.parent / metadata["samples_file"]).resolve()
    if raw_path.parent != path.parent.resolve():
        raise ValueError("样点文件必须在本会话目录")
    raw = raw_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != metadata["sha256"] or len(raw) != metadata["sample_count"]:
        raise ValueError("归档样点SHA256或点数不符")
    fields = ("capture_id", "period_ns", "trigger_index", "reason", "trigger_tick", "first_tick",
              "correlation_id", "config_id", "depth", "flags")
    return Capture(**{key: metadata[key] for key in fields}, samples=raw)


def load_saved_capture(path):
    """新归档读入已保存的原因；旧归档通过本份原始波形补充，不改旧文件。"""
    path = Path(path)
    capture = load_capture(path)
    metadata = json.loads(path.read_text(encoding='utf-8'))
    reads = tuple(t for t in decode_i2c(capture.samples, 1) if t.full_read)
    diagnosis = metadata.get('a_fault')
    if not isinstance(diagnosis, dict):
        diagnosis = capture_fault(capture, b_reads=reads)
    return SavedCapture(capture, path, reads, metadata.get('session_number', 0), diagnosis)
