from dataclasses import replace
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol import Assembler, Capture, Frame, Parser, capture_frames, crc16, encode
from session import Session, load_capture
from waveform import edge_points
from legacy_import import import_stream


def example(count=513):
    raw = bytes(i & 15 for i in range(count))
    return Capture(7, 20, min(count//2, 131072), 5, 10000+count//2,
                   10000, 3, 1, 262144, 0, raw)


class ProtocolTests(unittest.TestCase):
    def test_crc_vectors(self):
        self.assertEqual(crc16(b"123456789"), 0x29B1)
        self.assertEqual(zlib.crc32(b"123456789"), 0xCBF43926)

    def test_fragment_noise_and_payload_magic(self):
        frames = [Frame(0x20, i, i*100, 0, b"\xaa\x55"*40) for i in range(10)]
        raw = b"noise\xaa"+b"".join(map(encode, frames))
        parser = Parser()
        actual = []
        rng = random.Random(99)
        while raw:
            n = rng.randrange(1, 37)
            actual += parser.feed(raw[:n])
            raw = raw[n:]
        self.assertEqual(actual, frames)
        self.assertEqual(parser.crc_errors, 0)
        self.assertEqual(parser.sequence_gaps, 0)

    def test_crc_corruption_resynchronizes(self):
        first = bytearray(encode(Frame(0x10, 0, 0, 0, bytes(80))))
        first[35] ^= 1
        good = Frame(0x10, 1, 1, 0, bytes(80))
        parser = Parser()
        self.assertEqual(parser.feed(first+encode(good)), [good])
        self.assertGreater(parser.crc_errors, 0)

    def test_sequence_wrap_and_reset(self):
        parser = Parser()
        parser.feed(encode(Frame(0x10, 0xFFFFFFFF, 500, 0, bytes(80))))
        parser.feed(encode(Frame(0x10, 0, 600, 0, bytes(80))))
        self.assertEqual(parser.sequence_gaps, 0)
        parser.feed(encode(Frame(0x11, 0, 0, 0, bytes(80))))
        self.assertEqual(parser.resets, 1)
        self.assertEqual(parser.sequence_gaps, 0)

    def test_roundtrip_odd_and_full_depth(self):
        for count in (131, 513, 262144):
            c = example(count)
            assembler = Assembler()
            result = None
            for frame in capture_frames(c):
                result = assembler.accept(frame) or result
            self.assertEqual(result, c)
            self.assertEqual(assembler.errors, [])

    def test_missing_and_duplicate_block_rejected(self):
        for mode in ("missing", "duplicate"):
            frames = capture_frames(example())
            frames = frames[:1]+frames[2:] if mode == "missing" else frames[:2]+[frames[1]]+frames[2:]
            assembler = Assembler()
            self.assertFalse(any(assembler.accept(f) for f in frames))
            self.assertTrue(assembler.errors)

    def test_whole_crc_and_odd_padding_rejected(self):
        for mode in ("crc", "padding"):
            frames = capture_frames(example(131))
            i = -1 if mode == "crc" else 1
            payload = bytearray(frames[i].payload)
            payload[8 if mode == "crc" else -1] ^= 0x80
            frames[i] = replace(frames[i], payload=bytes(payload))
            assembler = Assembler()
            self.assertFalse(any(assembler.accept(f) for f in frames))
            self.assertTrue(assembler.errors)

    def test_bad_length_and_index_rejected(self):
        frame = capture_frames(example())[0]
        p = bytearray(frame.payload)
        struct.pack_into("<I", p, 8, 999999)
        assembler = Assembler()
        self.assertIsNone(assembler.accept(replace(frame, payload=bytes(p))))
        self.assertTrue(assembler.errors)

    def test_no_synthetic_wave_from_summary(self):
        p = bytearray(80)
        p[:6] = bytes((1, 0x68, 1, 6, 0x3B, 14))
        session = Session()
        session.feed(encode(Frame(0x21, 0, 100, 0, p)))
        self.assertIsNone(session.latest_b)
        self.assertIsNone(session.pinned)
        self.assertTrue(session.latest_summary[1]["full_read"])

    def test_archive_sha_and_pinned_immutable(self):
        with tempfile.TemporaryDirectory() as directory:
            session = Session(directory)
            first = example()
            for frame in capture_frames(first):
                session.feed(encode(frame))
            pinned = session.pinned
            second = replace(first, capture_id=8, reason=6)
            for frame in capture_frames(second, 100):
                session.feed(encode(frame))
            session.close()
            self.assertIs(session.pinned, pinned)
            self.assertEqual(load_capture(pinned.path), first)
            raw = pinned.path.with_suffix(".samples.bin")
            raw.write_bytes(b"\x0f"+raw.read_bytes()[1:])
            with self.assertRaises(ValueError):
                load_capture(pinned.path)

    def test_single_sample_glitch_kept_by_plot(self):
        c = replace(example(1000), samples=bytes(500)+b"\x01"+bytes(499))
        x, y = edge_points(c, 0)
        self.assertEqual(y, [0, 1, 0, 0])
        self.assertAlmostEqual(x[2]-x[1], 0.02)

    def test_legacy_02_03_offline_import(self):
        for version in (2, 3):
            with tempfile.TemporaryDirectory() as directory:
                raw_samples = bytes(range(16))
                raw = bytearray()
                payloads = [(0x40, struct.pack("<IHHBB2x",100,16,8,1,3 if version==2 else 15)),
                            (0x41, struct.pack("<H",0)+raw_samples),
                            (0x42, struct.pack("<HBB",16,sum(raw_samples)&255,1))]
                for seq,(kind,payload) in enumerate(payloads):
                    body = struct.pack("<2sBBHIIH",b"\xaa\x55",version,kind,seq,1000,1,len(payload))+payload
                    raw.extend(body+bytes((sum(body[2:])&255,)))
                self.assertEqual(import_stream(bytes(raw),directory),1)
                c = load_capture(next(Path(directory).glob("*.json")))
                self.assertEqual(c.period_ns,100)
                self.assertEqual(c.samples,raw_samples)


if __name__ == "__main__":
    unittest.main()
