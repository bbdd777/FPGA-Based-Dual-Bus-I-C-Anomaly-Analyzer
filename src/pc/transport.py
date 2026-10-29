"""串口接收、解析/保存与界面分离。UI堵塞不会阻塞串口接收。"""
from datetime import datetime
from pathlib import Path
from queue import Queue, Empty, Full
from threading import Event, Thread
import time

from session import Session


class Receiver:
    def __init__(self, port=None, baud=1000000, directory="captures", replay=None, serial_factory=None):
        self.port, self.baud = port, baud
        self.directory = Path(directory) / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.replay = Path(replay) if replay else None
        self.serial_factory = serial_factory
        self.stop_requested = Event()
        self.input = Queue(maxsize=256)  # 每次最多64KiB，约16MiB缓冲；不无界增长。
        self.updates = Queue(maxsize=1)  # 只合并UI快照，原始字节和记录不会在此丢弃。
        self.error = ""
        self.reader = Thread(target=self._read, name="serial_reader", daemon=True)
        self.processor = Thread(target=self._process, name="parser_archive", daemon=True)

    def start(self):
        self.processor.start()
        self.reader.start()

    def stop(self):
        self.stop_requested.set()

    def _put(self, data):
        # 在串口读取完成时记电脑时钟，不能等解析/绘图后再记，否则会混入排队延迟。
        received_at = datetime.now().astimezone().isoformat(timespec='milliseconds')
        try:
            self.input.put((data, received_at), timeout=0.5)
        except Full:
            self.error = "接收队列满，流已中止；本会话不再宣称无损"
            self.stop_requested.set()

    def _read(self):
        try:
            if self.replay:
                # 仿真hex是线上字节的逐行十六进制；普通文件按二进制串口流回放。
                with self.replay.open("rb") as stream:
                    while not self.stop_requested.is_set():
                        data = stream.read(49152 if self.replay.suffix == ".hex" else 16384)
                        if not data:
                            break
                        self._put(bytes.fromhex(data.decode("ascii")) if self.replay.suffix == ".hex" else data)
            else:
                import serial
                factory = self.serial_factory or serial.serial_for_url
                with factory(self.port, baudrate=self.baud, bytesize=8, parity="N", stopbits=1,
                             timeout=0.05, xonxoff=False, rtscts=False, dsrdtr=False) as stream:
                    while not self.stop_requested.is_set():
                        self._put(stream.read(min(65536, max(1, stream.in_waiting))))
        except Exception as error:
            self.error = str(error)
        finally:
            # 即使用户断开，也先处理已接收的所有字节并关闭文件。
            self.input.put(None)

    def _publish(self, session, closed=False):
        snapshot = session.snapshot() | {"connection_error": self.error, "closed": closed,
                                         "directory": str(self.directory)}
        try:
            self.updates.get_nowait()
        except Empty:
            pass
        self.updates.put_nowait(snapshot)

    def _process(self):
        session = None
        try:
            session = Session(self.directory, input_mode='replay' if self.replay else 'live')
            last_update = 0
            while True:
                try:
                    data = self.input.get(timeout=0.1)
                except Empty:
                    self._publish(session)
                    continue
                if data is None:
                    break
                data, received_at = data
                session.feed(data, host_received_at=received_at)
                if time.monotonic()-last_update >= 0.1:
                    self._publish(session)
                    last_update = time.monotonic()
        except Exception as error:
            self.error = str(error)
            self.stop_requested.set()
        finally:
            if session:
                session.close()
                self._publish(session, closed=True)
