"""RTL生成的真实线上字节 -> 正式解析/存档/原始I2C解码的整链验收。"""
from collections import Counter
from pathlib import Path
import json
from session import Session


def main():
    root = Path(__file__).resolve().parent
    verify = root / "verification"
    verify.mkdir(exist_ok=True)
    raw = bytes.fromhex((root.parent / "vivado_prj/verification/sim/core_stream.hex").read_text())
    session = Session(verify / "replay_session")
    for offset in range(0, len(raw), 137):
        session.feed(raw[offset:offset+137])
    captures = list(session.captures)
    assert len(captures) == 3
    assert [s.capture.reason for s in captures] == [5, 6, 5]
    assert all(len(s.capture.samples) == 262144 and s.capture.trigger_index == 131072 for s in captures)
    assert all(len(s.b_reads) == 1 for s in captures)
    assert all(s.b_reads[0].data == bytes(range(0x20, 0x2E)) for s in captures)
    assert session.pinned is captures[0] and session.latest_b is captures[2]
    assert session.parser.crc_errors == session.parser.sequence_gaps == 0
    assert not session.assembler.errors
    correlations = [r for r in session.records if r["kind"] == 0x32]
    assert [r["fault"] for r in correlations] == [1, 2]
    assert all(r["result"] == 1 and r["elapsed_ticks"] <= 50000 for r in correlations)
    reads = [r for r in session.records if r["kind"] == 0x33]
    assert len(reads) == 2 and all(r["result"] == 1 for r in reads)
    assert all(not any(r.get("fifo_drops", ())) for r in session.records if r["kind"] == 0x10)
    # 物理UART 1M逐位解码的结果须和发送握手字节完全相同。
    sim = root.parent / "vivado_prj/verification/sim"
    physical = bytes.fromhex((sim / "stream_1m_serial.hex").read_text())
    assert physical == bytes.fromhex((sim / "stream_1m.hex").read_text())
    small = Session()
    small.feed(physical)
    assert len(small.captures) == 1
    c = small.captures[0].capture
    assert len(c.samples) == 131
    assert c.samples == bytes((c.first_tick+i) & 15 for i in range(131))
    busy = Session()
    busy.feed(bytes.fromhex((sim / "busy_stream.hex").read_text()))
    assert busy.parser.crc_errors == busy.parser.sequence_gaps == 0 and not busy.assembler.errors
    assert sum(r["kind"] == 0x21 and r["full_read"] for r in busy.records) == 2
    assert sum(r["kind"] == 0x32 and r["result"] == 1 for r in busy.records) == 1
    assert sum(r["kind"] == 0x33 and r["result"] == 1 for r in busy.records) == 1
    assert busy.status["missed_captures"] == 1
    assert len(busy.captures) == 1 and busy.latest_b is None
    bad = Session()
    bad.feed(bytes.fromhex((sim / "bad_reads_stream.hex").read_text()))
    assert bad.parser.crc_errors == bad.parser.sequence_gaps == 0 and not bad.assembler.errors
    assert [r["result"] for r in bad.records if r["kind"] == 0x33] == [2,2,2,2,3]
    assert not any(r.get("full_read", False) for r in bad.records)
    result = dict(passed=True, hardware_tested=False, stream_bytes=len(raw),
                  captures=[dict(id=s.capture.capture_id, points=len(s.capture.samples),
                                 reason=s.capture.reason, full_b_reads=len(s.b_reads)) for s in captures],
                  fixed_fault=captures[0].capture.capture_id, latest_b=captures[-1].capture.capture_id,
                  crc_errors=0, sequence_gaps=0, uart_1m_physical_bytes=len(physical),
                  busy_upload_live_reads=2, busy_missed_raw_captures=1,
                  invalid_reads_rejected=4, missing_stop_timeouts=1,
                  records=dict(Counter(hex(r["kind"]) for r in session.records)))
    session.close()
    (verify / "replay_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
