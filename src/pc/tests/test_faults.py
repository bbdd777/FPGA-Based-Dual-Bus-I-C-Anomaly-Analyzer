"""检查原因与接替结果的关联，避免把旧图/其他会话结果混成当前故障。"""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from faults import update_a_fault, fault_title, fault_detail, backup_status
from protocol import Frame, encode
from protocol import Capture
from faults import capture_fault
from session import Session

CONFIG = dict(period_ns=20, low_ticks=25000)

def fault(kind=1, tick=100, session=1):
    return dict(kind=0x30, fault=kind, address=0x6A, tick=tick, session_number=session)

def correlation(result=1, cause=1, start=100, session=1):
    return dict(kind=0x32, fault=cause, start_tick=start, end_tick=start+2000,
                result=result, elapsed_ticks=2000, correlation_id=1, session_number=session)

class FaultTests(unittest.TestCase):
    def test_capture_reason_alone_does_not_guess_a_cause(self):
        capture = Capture(1, 20, 128, 5, 128, 0, 1, 1, 256, 0, bytes([15])*256)
        self.assertIn('未记录', fault_title(capture_fault(capture)))
    def test_nack_address_then_ack_is_not_complete_read(self):
        info = update_a_fault(None, fault(), CONFIG)
        self.assertIn('NACK', fault_title(info))
        self.assertIn('0x6A', fault_detail(info))
        info = update_a_fault(info, correlation(), CONFIG)
        self.assertIn('等待完整读取', backup_status(info)[0])
        info = update_a_fault(info, dict(kind=0x33, result=1, correlation_id=1, session_number=1), CONFIG)
        self.assertIn('14字节完整读取', backup_status(info)[0])

    def test_low_timeout_ignores_stale_address(self):
        info = update_a_fault(None, fault(kind=2), CONFIG)
        self.assertIn('SCL', fault_title(info))
        self.assertIn('500', fault_detail(info))
        self.assertNotIn('0x6A', fault_detail(info))
        info = update_a_fault(info, correlation(result=2, cause=2), CONFIG)
        self.assertIn('地址应答超时', backup_status(info)[0])
        self.assertIn('SCL', fault_title(info))

    def test_normal_updates_retain_history_and_reset_clears_recent(self):
        info = update_a_fault(None, fault(), CONFIG)
        self.assertEqual(update_a_fault(info, dict(kind=0x21), CONFIG), info)
        self.assertIsNone(update_a_fault(info, dict(kind=0x11), CONFIG))

    def test_late_and_other_session_results_do_not_relabel_latest(self):
        info = update_a_fault(None, fault(kind=2, tick=500, session=2), CONFIG)
        info = update_a_fault(info, correlation(cause=2, start=500, session=2), CONFIG)
        for record in (correlation(start=100, session=2), fault(tick=100, session=2),
                       correlation(session=1), fault(session=1),
                       dict(kind=0x33, result=1, correlation_id=1, session_number=1)):
            info = update_a_fault(info, record, CONFIG)
        self.assertEqual(info['fault'], 2)
        self.assertNotIn('read_result', info)
        info = update_a_fault(info, dict(kind=0x33, result=3, correlation_id=1, session_number=2), CONFIG)
        self.assertIn('完整读取超时', backup_status(info)[0])

    def test_late_fault_record_keeps_same_correlation_result(self):
        info = update_a_fault(None, correlation(), CONFIG)
        info = update_a_fault(info, dict(kind=0x33, result=1, correlation_id=1, session_number=1), CONFIG)
        info = update_a_fault(info, fault(), CONFIG)
        self.assertIn('0x6A', fault_detail(info))
        self.assertEqual(info['read_result'], 1)

    def test_session_snapshot_keeps_event_after_log_display_scrolls(self):
        session = Session()
        payload = bytearray(80); payload[:4] = bytes((0, 1, 0x6A, 1))
        session.feed(encode(Frame(0x30, 1, 100, 0, bytes(payload))))
        for sequence in range(2, 110):
            session.feed(encode(Frame(0x10, sequence, sequence*100, 0, bytes(80))))
        snap = session.snapshot()
        self.assertFalse(any(r['kind'] == 0x30 for r in snap['records']))
        self.assertEqual(snap['latest_a_fault']['address'], 0x6A)
        session.close()

if __name__ == '__main__':
    unittest.main()
