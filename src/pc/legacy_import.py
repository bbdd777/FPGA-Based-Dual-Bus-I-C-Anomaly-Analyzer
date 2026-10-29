"""仅离线导入阶段八/九02/03格式，不改变正式实时接收的04协议。"""
import argparse
from pathlib import Path
import struct
from protocol import Capture
from session import Session

HEADER = struct.Struct("<2sBBHIIH")


def import_stream(raw, directory):
    session = Session(directory)
    session.session_number = 800  # 与新协议会话分开标识
    pending = None
    offset = 0
    imported = 0
    try:
        while offset+17 <= len(raw):
            start = raw.find(b"\xaa\x55", offset)
            if start < 0:
                break
            offset = start+1
            if start+16 > len(raw):
                break
            _, version, kind, sequence, tick, cap_id, size = HEADER.unpack_from(raw, start)
            end = start+17+size
            if version not in (2,3) or size > 258 or end > len(raw):
                continue
            body = raw[start:end]
            if sum(body[2:-1]) & 255 != body[-1]:
                pending = None
                continue
            offset = end
            p = body[16:-1]
            if kind == 0x40:
                if size != 12:
                    raise ValueError("旧开始帧长度错误")
                period, count, index, reason, channels = struct.unpack_from("<IHHBB", p)
                if not (period > 0 and 0 < count <= 32768 and index < count and channels in (3,15)):
                    raise ValueError("旧采样元数据错误")
                pending = dict(period=period, count=count, index=index, reason=reason,
                               tick=tick, id=cap_id, version=version, samples=bytearray(), seq=sequence)
            elif kind in (0x41,0x42) and pending:
                s = pending
                if (cap_id != s["id"] or tick != s["tick"] or version != s["version"]):
                    raise ValueError("旧波形元数据变化")
                if kind == 0x41:
                    block_offset = struct.unpack_from("<H", p)[0]
                    if block_offset != len(s["samples"]) or any(v > 15 for v in p[2:]):
                        raise ValueError("旧波形块乱序或非法样点")
                    s["samples"].extend(p[2:])
                    if len(s["samples"]) > s["count"]:
                        raise ValueError("旧波形块超长")
                else:
                    count, checksum, reason = struct.unpack("<HBB", p)
                    samples = bytes(s["samples"])
                    if (count != s["count"] or len(samples) != count or reason != s["reason"]
                            or sum(samples) & 255 != checksum):
                        raise ValueError("旧完整波形校验失败")
                    tick = s["tick"] if s["tick"] >= s["index"] else s["tick"] + (1 << 32)
                    session._save(Capture(s["id"], s["period"], s["index"], reason, tick,
                                          tick-s["index"], 0, 0, 32768, 0x80000000, samples))
                    imported += 1
                    pending = None
        return imported
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="离线导入02/03串口流，输出可打开的归档JSON")
    parser.add_argument("input")
    parser.add_argument("output")
    args = parser.parse_args()
    print("已导入", import_stream(Path(args.input).read_bytes(), args.output), "份旧波形")
