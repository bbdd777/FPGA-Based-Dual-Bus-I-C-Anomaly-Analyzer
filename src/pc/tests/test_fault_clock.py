"""电脑接收时刻应来自接收线程，并随首次故障保持，不等同FPGA源时基。"""
from pathlib import Path
import json
import struct
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from faults import update_a_fault, receipt_text, capture_fault
from protocol import Frame, encode, Capture
from session import Session
from transport import Receiver
from unittest.mock import patch
from datetime import datetime

T0 = '2026-10-22T15:10:00.123+08:00'
T1 = '2026-10-22T15:10:01.456+08:00'


def fault_frame():
    return encode(Frame(0x30, 1, 100, 0, bytes((0, 1, 0x6A))+bytes(77)))


class FaultClockTests(unittest.TestCase):
    def test_fragment_uses_completion_batch_and_saves_log(self):
        with tempfile.TemporaryDirectory() as directory:
            session = Session(directory, input_mode='live')
            raw = fault_frame()
            session.feed(raw[:-3], T0)
            self.assertIsNone(session.latest_a_fault)
            session.feed(raw[-3:], T1)
            self.assertEqual(session.latest_a_fault['host_received_at'], T1)
            self.assertIn('电脑接收时间', receipt_text(session.latest_a_fault))
            session.close()
            record = json.loads((Path(directory)/'events.jsonl').read_text().splitlines()[0])
            self.assertEqual(record['host_received_at'], T1)

    def test_association_and_late_raw_keep_first_receipt(self):
        correlation = dict(kind=0x32, fault=1, start_tick=100, session_number=1,
                           correlation_id=1, result=1, elapsed_ticks=20,
                           host_received_at=T0, host_received_order=1, input_mode='live')
        raw = dict(kind=0x30, fault=1, tick=100, session_number=1, address=0x6A,
                   host_received_at=T1, host_received_order=2, input_mode='live')
        current = update_a_fault(None, correlation, {})
        current = update_a_fault(current, raw, {})
        self.assertEqual(current['host_received_at'], T0)
        # 归档先找到较晚到达的原始故障时，仍应采用最早收到的关联记录时间。
        capture = Capture(1, 20, 1, 5, 100, 99, 1, 1, 3, 0, bytes([15])*3)
        self.assertEqual(capture_fault(capture, [correlation, raw], session_number=1)['host_received_at'], T0)
        read = dict(kind=0x33, correlation_id=1, result=1, session_number=1, host_received_at=T1)
        self.assertEqual(update_a_fault(current, read, {})['host_received_at'], T0)

    def test_replay_and_old_unknown_are_not_hardware_wall_time(self):
        session = Session(input_mode='replay')
        session.feed(fault_frame(), T0)
        self.assertIn('回放接收时间', receipt_text(session.latest_a_fault))
        self.assertIn('未记录', receipt_text({'fault': 1}))
        self.assertIn('等待异常', receipt_text(None))
        # 新故障用新源tick和实收时刻。
        session.feed(encode(Frame(0x30, 2, 200, 0, bytes((0, 2, 0x68))+bytes(77))), T1)
        self.assertEqual(session.latest_a_fault['host_received_at'], T1)

    def test_receiver_attaches_clock_before_processor_queue(self):
        receiver = Receiver(port='not-opened')
        with patch('transport.datetime') as clock:
            clock.now.return_value = datetime.fromisoformat(T0)
            receiver._put(b'bytes')
        data, timestamp = receiver.input.get_nowait()
        self.assertEqual(data, b'bytes')
        self.assertEqual(timestamp, T0)
