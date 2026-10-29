"""检查监听字节的符号、完整性和历史读数标记，避免异常时显示伪读数。"""
from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from decoded_panel import sensor_values, decoded_text
from protocol import Frame, encode
from session import Session


VALUES = (-32768, -1, 32767, -1234, 123, -456, 0)


def transaction(sequence=1, bus=0, valid=True):
    payload = bytearray(80)
    data = struct.pack('>7h', *VALUES) if valid else b'\x3b'
    payload[:6] = bytes((bus, 0x68, 1 if valid else 0, 6 if valid else 1, 0x3B, len(data)))
    struct.pack_into('<QQ', payload, 8, sequence*100, sequence*100+50)
    payload[24:24+len(data)] = data
    return encode(Frame(0x20+bus, sequence, sequence*100+50, 0, bytes(payload)))


class DecodedPanelTests(unittest.TestCase):
    def test_signed_values_for_both_devices(self):
        session = Session()
        session.feed(transaction()+transaction(2, 1))
        text = decoded_text(session.snapshot())
        self.assertIn('设备A', text)
        self.assertIn('设备B', text)
        self.assertEqual(text.count('AX=-32768'), 2)
        self.assertEqual(text.count('AY=-1'), 2)
        self.assertEqual(text.count('AZ=32767'), 2)
        self.assertIn('TEMP=-1234', text)
        self.assertIn('GY=-456', text)
        self.assertIn('80 00 FF FF 7F FF FB', text)

    def test_invalid_and_wrong_pointer_have_no_sensor_values(self):
        record = dict(full_read=True, count=14, pointer=0x3B, flags=3, data='00 '*14)
        self.assertIsNone(sensor_values(record))
        record.update(flags=6, pointer=0x75)
        self.assertIsNone(sensor_values(record))
        self.assertIn('尚未收到', decoded_text({}))
        self.assertNotIn('AX=', decoded_text({}))

    def test_old_valid_read_retained_and_marked_after_failure(self):
        session = Session()
        session.feed(transaction()+transaction(2, valid=False))
        session.records.clear()  # 不依赖显示日志是否已经滚出。
        text = decoded_text(session.snapshot())
        self.assertIn('上次有效读数（非当前事务）', text)
        self.assertIn('异常/不完整事务', text)
        self.assertIn('AX=-32768', text)

    def test_new_config_clears_prior_read_and_fault(self):
        session = Session()
        session.feed(transaction())
        session.feed(encode(Frame(0x30, 2, 200, 0, bytes((0, 1, 0x6A))+bytes(77))))
        self.assertIn('异常记录', decoded_text(session.snapshot()))
        session.feed(encode(Frame(0x11, 0, 0, 0, bytes(80))))
        self.assertFalse(session.latest_sensor_summary)
        self.assertFalse(session.latest_bus_fault)
        self.assertNotIn('AX=', decoded_text(session.snapshot()))
