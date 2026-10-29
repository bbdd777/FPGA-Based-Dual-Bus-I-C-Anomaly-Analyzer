"""回归：低超时切换到地址NACK后，自动视图只能使用完整、校验通过的新故障。"""
from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from faults import fault_view_text
from protocol import Capture, Frame, capture_frames, encode
from session import Session


def fault_capture(capture_id, reason=5):
    return Capture(capture_id, 20, 32, reason, capture_id*1000+32,
                   capture_id*1000, capture_id, 1, 262144, 0, bytes([15])*65)


def feed_capture(session, capture, sequence=0):
    for frame in capture_frames(capture, sequence):
        session.feed(encode(frame))


class FaultFollowTests(unittest.TestCase):
    def test_latest_complete_fault_advances_but_normal_capture_keeps_it(self):
        session = Session()
        first, second = fault_capture(47), fault_capture(51, reason=4)
        feed_capture(session, first)
        first_saved = session.latest_fault
        feed_capture(session, second, 10)
        self.assertEqual(session.snapshot()['latest_fault'].capture, second)
        self.assertIs(session.pinned, first_saved)  # 首份历史证据仍保留。
        feed_capture(session, fault_capture(52, reason=6), 20)
        self.assertEqual(session.latest_fault.capture, second)

    def test_partial_or_corrupt_capture_does_not_replace_complete_evidence(self):
        for corrupt in (False, True):
            with self.subTest(corrupt=corrupt):
                session = Session()
                feed_capture(session, fault_capture(47))
                previous = session.latest_fault
                frames = capture_frames(fault_capture(51), 10)
                for frame in frames[:-1]:
                    session.feed(encode(frame))
                self.assertIs(session.latest_fault, previous)
                self.assertTrue(session.snapshot()['receiving_wave'])
                end = frames[-1]
                if corrupt:
                    payload = bytearray(end.payload)
                    payload[8] ^= 1  # 外层帧CRC正确，但整份样点CRC错误。
                    end = replace(end, payload=bytes(payload))
                session.feed(encode(end))
                if corrupt:
                    self.assertIs(session.latest_fault, previous)
                    self.assertEqual(session.assembler.error_count, 1)
                else:
                    self.assertEqual(session.latest_fault.capture.capture_id, 51)

    def test_event_before_wave_is_marked_waiting(self):
        session = Session()
        feed_capture(session, fault_capture(47))
        event = Frame(0x30, 10, 51000, 0, bytes((0, 1, 0x6A))+bytes(77))
        session.feed(encode(event))
        text = fault_view_text(session.latest_fault, session.latest_a_fault)
        self.assertIn('捕获#47', text)
        self.assertIn('最新异常尚无对应完整波形', text)

    def test_manual_status_and_matching_require_session_and_correlation(self):
        session = Session()
        feed_capture(session, fault_capture(51))
        recent = dict(session_number=0, correlation_id=51)
        self.assertIn('自动跟随最新完整故障', fault_view_text(session.latest_fault, recent))
        self.assertIn('手动固定', fault_view_text(session.latest_fault, recent, manual=True))
        recent['session_number'] = 1  # FPGA重启后的相同关联号不是同一次故障。
        self.assertIn('尚无对应完整波形', fault_view_text(session.latest_fault, recent))


if __name__ == '__main__':
    unittest.main()
