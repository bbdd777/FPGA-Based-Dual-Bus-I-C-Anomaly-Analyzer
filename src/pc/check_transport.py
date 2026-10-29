"""不消费UI快照时，后台仍应收齐并归档全部RTL字节。绝不打开COM口。"""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import time
from transport import Receiver


def main():
    root = Path(__file__).resolve().parent
    source = root.parent / "vivado_prj/verification/sim/core_stream.hex"
    expected = bytes.fromhex(source.read_text())
    with TemporaryDirectory() as directory:
        receiver = Receiver(replay=source, directory=directory)
        receiver.start()
        # 完全不取UI队列，模拟绘图/导出暂时占用主线程。
        receiver.reader.join(timeout=10)
        receiver.processor.join(timeout=20)
        assert not receiver.reader.is_alive() and not receiver.processor.is_alive()
        snapshot = receiver.updates.get_nowait()
        assert snapshot["closed"] and not snapshot["connection_error"]
        assert snapshot["bytes"] == len(expected)
        assert snapshot["pinned"].capture.capture_id == 1
        assert snapshot["latest_b"].capture.capture_id == 3
        assert (receiver.directory / "serial.raw.bin").read_bytes() == expected
        assert len(list(receiver.directory.glob("*.samples.bin"))) == 3
        assert receiver.updates.maxsize == 1
    result = dict(passed=True, serial_opened=False, ui_consumer_running=False,
                  raw_bytes=len(expected), all_captures_archived=True)
    (root/"verification/transport_result.json").write_text(json.dumps(result, indent=2),encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
