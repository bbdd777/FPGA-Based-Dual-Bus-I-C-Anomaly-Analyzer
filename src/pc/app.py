"""Tkinter正式上位机：自动跟随最新故障，支持手动固定，B正常波形独立更新。"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from queue import Empty
import csv
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from matplotlib import rcParams
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

from session import load_saved_capture
from transport import Receiver
from waveform import draw_capture, draw_waiting, layout_waveform
from waveform_navigation import WaveformNavigation
from waveform_scroll import WaveformScroll
from decoded_panel import decoded_text
from faults import backup_status, capture_fault, fault_detail, fault_title, fault_view_text, receipt_text

rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
rcParams["axes.unicode_minus"] = False


def export_csv(saved, path):
    c = saved.capture
    with open(path, "w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(("index", "relative_ns", "source_tick", "A_SCL", "A_SDA", "B_SCL", "B_SDA"))
        for index, value in enumerate(c.samples):
            writer.writerow((index, (index-c.trigger_index)*c.period_ns, c.first_tick+index,
                             *((value >> bit) & 1 for bit in range(4))))


class Application:
    def __init__(self, root):
        self.root, self.receiver = root, None
        self.snapshot = {}
        self.pinned = self.latest_b = None
        self.drawn_fault = self.drawn_live = None
        self.local_pin = False
        self._diagnosis_cache = {}
        self.exports = ThreadPoolExecutor(max_workers=1, thread_name_prefix="export")
        self.export_future = None
        root.title("FPGA 双总线异常分析仪 · 50MSa/s")
        # 留出标题栏/任务栏空间；新增原因提示后仍让两个波形区适配当前屏幕。
        width = max(760, min(1440, root.winfo_screenwidth()-60))
        height = max(600, min(960, root.winfo_screenheight()-100))
        root.geometry(f"{width}x{height}")
        self._build()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.poll)

    def _build(self):
        bar = ttk.Frame(self.root, padding=8)
        bar.pack(fill="x")
        ttk.Label(bar, text="串口").pack(side="left")
        self.port = ttk.Combobox(bar, width=15)
        self.port.pack(side="left", padx=4)
        ttk.Button(bar, text="刷新", command=self.refresh_ports).pack(side="left")
        self.baud = ttk.Combobox(bar, values=(1000000, 460800, 921600, 2000000), width=10)
        self.baud.set(1000000)
        self.baud.pack(side="left", padx=8)
        self.connect_button = ttk.Button(bar, text="连接监测", command=self.connect)
        self.connect_button.pack(side="left")
        ttk.Button(bar, text="断开", command=self.disconnect).pack(side="left", padx=4)
        ttk.Button(bar, text="回放串口文件", command=self.replay).pack(side="left")
        ttk.Button(bar, text="打开归档波形", command=self.open_archive).pack(side="left", padx=4)
        ttk.Label(bar, text="50MSa/s · 262144点 · 20ns/点 · 自动取证", foreground="#225b88").pack(side="right")

        self.connection = tk.StringVar(value="未连接。连接后显示设备实际状态，不需要点击布防。")
        ttk.Label(self.root, textvariable=self.connection, padding=(8, 2)).pack(fill="x")
        self.health = tk.StringVar(value="协议04 / CRC16 + 全波形CRC32")
        ttk.Label(self.root, textvariable=self.health, padding=(8, 2)).pack(fill="x")

        # 异常事件先到，完整波形稍后上传；本份原因始终跟随实际显示的捕获。
        alert = ttk.Labelframe(self.root, text="最近一次A异常（保留事件记录）", padding=(8, 4))
        alert.pack(fill="x", padx=8, pady=(2, 4))
        alert.columnconfigure(0, weight=1)
        alert.columnconfigure(1, weight=1)
        alert.columnconfigure(2, weight=1)
        self.a_fault_title = tk.StringVar(value="尚未收到A异常")
        self.a_fault_detail = tk.StringVar(value=fault_detail(None))
        self.backup_result = tk.StringVar(value=backup_status(None)[0])
        self.a_fault_received = tk.StringVar(value=receipt_text(None))
        self.a_fault_heading = ttk.Label(alert, textvariable=self.a_fault_title,
                                        font=("Microsoft YaHei", 14, "bold"), foreground="#66717d")
        self.a_fault_heading.grid(row=0, column=0, sticky="w")
        self.backup_heading = ttk.Label(alert, textvariable=self.backup_result,
                                       font=("Microsoft YaHei", 11, "bold"), foreground="#66717d")
        self.backup_heading.grid(row=0, column=2, sticky="e")
        ttk.Label(alert, textvariable=self.a_fault_received, foreground='#225b88',
                  font=('Microsoft YaHei', 10), wraplength=350).grid(row=0, column=1, padx=10)
        detail_label = ttk.Label(alert, textvariable=self.a_fault_detail, foreground="#5b6571")
        detail_label.grid(row=1, column=0, columnspan=3, sticky="w")
        alert.bind("<Configure>", lambda e: detail_label.configure(wraplength=max(300, e.width-24)))

        body = ttk.Panedwindow(self.root, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=4)
        self.plot_scroll = WaveformScroll(body)
        body.add(self.plot_scroll, weight=5)
        views = self.plot_scroll.content
        fault = ttk.Labelframe(views, text="故障证据：A故障与首次B读出，共用本次捕获时间轴")
        live = ttk.Labelframe(views, text="最新B正常原始波形：独立捕获，更新不会覆盖上方故障")
        fault.pack(fill='x')
        live.pack(fill='x', pady=(6, 0))
        self.fault_label = tk.StringVar(value="等待第一份完整故障波形")
        self.fault_view_status = tk.StringVar(value=fault_view_text(None, None))
        self.fault_view_status_label = ttk.Label(fault, textvariable=self.fault_view_status,
                                               foreground="#225b88")
        self.fault_view_status_label.pack(fill="x")
        self.fixed_fault_reason = tk.StringVar(value="本份异常原因：等待完整故障证据")
        self.fixed_reason_label = ttk.Label(fault, textvariable=self.fixed_fault_reason,
                                           font=("Microsoft YaHei", 11, "bold"), foreground="#b42318")
        self.fixed_reason_label.pack(fill="x")
        def wrap_fault_labels(event):
            width = max(300, event.width-24)
            self.fixed_reason_label.configure(wraplength=width)
            self.fault_view_status_label.configure(wraplength=width)
        fault.bind("<Configure>", wrap_fault_labels)
        self.live_label = tk.StringVar(value="尚无完整B原始波形；仅收到摘要时不绘制理想波形")
        self.fault_figure = Figure(figsize=(10, 3.6), dpi=100)
        self.live_figure = Figure(figsize=(10, 2.2), dpi=100)
        # 未连接时先建立四路/两路空坐标，通道名称始终可见，不再是一整块白板。
        draw_waiting(self.fault_figure, (0, 1, 2, 3))
        draw_waiting(self.live_figure, (2, 3))
        self.fault_canvas = FigureCanvasTkAgg(self.fault_figure, fault)
        self.live_canvas = FigureCanvasTkAgg(self.live_figure, live)
        self.navigation = {}
        for name, container, canvas in (("fault", fault, self.fault_canvas), ("live", live, self.live_canvas)):
            toolbar = NavigationToolbar2Tk(canvas, container, pack_toolbar=False)
            toolbar.pack(side="bottom", fill="x")
            canvas.get_tk_widget().pack(fill="both", expand=True)
            self.plot_scroll.register_plot(canvas)
            self.navigation[name] = WaveformNavigation(canvas, toolbar)
            ttk.Label(toolbar, text="波形滚轮缩放 · 空白滚页面 · 左键平移", foreground="#225b88").pack(side="right")
            # 放进工具条，避免窗口缩小时被扩展画布挤到可见区域以外。
            ttk.Button(toolbar, text="查看完整采样窗口", command=lambda view=name: self.show_full(view)).pack(
                side="right", padx=5)
            # 窗口宽度改变只重排边距，不改变时间轴和各行应有的高度。
            canvas.mpl_connect("resize_event", lambda event: layout_waveform(event.canvas.figure))

        side = ttk.Frame(body, width=335)
        body.add(side, weight=1)
        ttk.Label(side, text="捕获列表（双击固定故障证据）").pack(anchor="w")
        self.capture_list = ttk.Treeview(side, columns=("reason", "points"), height=8)
        self.capture_list.heading("#0", text="会话 / 捕获ID")
        self.capture_list.heading("reason", text="本份异常原因")
        self.capture_list.heading("points", text="点数")
        self.capture_list.column("#0", width=115)
        self.capture_list.column("reason", width=135)
        self.capture_list.column("points", width=75)
        self.capture_list.pack(fill="x")
        self.capture_list.bind("<Double-1>", self.select_pin)
        ttk.Button(side, text="跟随最新故障", command=self.auto_pin).pack(fill="x", pady=4)
        ttk.Button(side, text="导出固定故障 CSV", command=self.export).pack(fill="x")
        ttk.Button(side, text="导出固定故障 PNG", command=self.export_png).pack(fill="x", pady=4)
        notebook = ttk.Notebook(side)
        notebook.pack(fill='both', expand=True)
        decoded = ttk.Frame(notebook)
        events = ttk.Frame(notebook)
        notebook.add(decoded, text='A/B监听译码')
        notebook.add(events, text='事务与异常记录')
        self.decoded_text = tk.Text(decoded, width=43, height=20, wrap='word', font=('Consolas', 9))
        scroll = ttk.Scrollbar(decoded, orient='vertical', command=self.decoded_text.yview)
        scroll.pack(side='right', fill='y')
        self.decoded_text.configure(yscrollcommand=scroll.set)
        self.decoded_text.pack(fill='both', expand=True)
        self._decoded_display = None
        self.show_decoded({})
        self.records_text = tk.Text(events, width=43, height=20, wrap="word", font=("Consolas", 9))
        event_scroll = ttk.Scrollbar(events, orient='vertical', command=self.records_text.yview)
        event_scroll.pack(side='right', fill='y')
        self.records_text.configure(yscrollcommand=event_scroll.set)
        self.records_text.pack(fill="both", expand=True)
        self.refresh_ports()

    def refresh_ports(self):
        try:
            from serial.tools import list_ports
            self.port["values"] = [p.device for p in list_ports.comports()]
            if not self.port.get() and self.port["values"]:
                self.port.set(self.port["values"][0])
        except ImportError:
            self.connection.set("缺少pySerial，请先安装requirements.txt")

    def _start(self, **kwargs):
        if self.receiver and self.receiver.processor.is_alive():
            messagebox.showinfo("接收仍在运行", "请先断开，等待已有数据保存完成。")
            return
        self.receiver = Receiver(directory=Path(__file__).parent / "captures", **kwargs)
        self.snapshot = {}
        self.connect_button.configure(state="disabled")
        self.show_decoded({})
        self.a_fault_received.set(receipt_text(None))
        self.receiver.start()
        self.connection.set("正在接收；等待有效配置/状态帧确认设备工作状态")

    def connect(self):
        if self.port.get():
            self._start(port=self.port.get(), baud=int(self.baud.get()))

    def disconnect(self):
        if self.receiver:
            self.receiver.stop()

    def replay(self):
        path = filedialog.askopenfilename(filetypes=(("串口流", "*.bin *.hex"), ("全部", "*.*")))
        if path:
            self._start(replay=path)

    def open_archive(self):
        path = filedialog.askopenfilename(filetypes=(("波形元数据", "*.json"),))
        if not path:
            return
        try:
            self.pinned = load_saved_capture(path)
            self.local_pin = True
            self.draw()
        except Exception as error:
            messagebox.showerror("无法打开归档", str(error))

    def auto_pin(self):
        self.local_pin = False
        self.pinned = self.snapshot.get("latest_fault")
        self.draw()

    def select_pin(self, _event=None):
        selection = self.capture_list.selection()
        for saved in self.snapshot.get("captures", ()):
            if selection and selection[0] == f"{saved.session_number}:{saved.capture.capture_id}":
                self.pinned, self.local_pin = saved, True
                self.draw()
                return

    def apply_snapshot(self, snapshot):
        self.snapshot = snapshot
        self.show_decoded(snapshot)
        if not self.local_pin:
            self.pinned = snapshot.get("latest_fault")
        if snapshot.get("latest_b"):
            self.latest_b = snapshot["latest_b"]
        self.capture_list.delete(*self.capture_list.get_children())
        recent = snapshot.get("latest_a_fault")
        self.a_fault_received.set(receipt_text(recent))
        self.a_fault_title.set(fault_title(recent) if recent else "尚未收到A异常")
        self.a_fault_heading.configure(foreground="#b42318" if recent else "#66717d")
        self.a_fault_detail.set(fault_detail(recent))
        backup, color = backup_status(recent)
        self.backup_result.set(backup)
        self.backup_heading.configure(foreground=color)
        for saved in snapshot.get("captures", ()):
            c = saved.capture
            info = self.diagnosis(saved)
            reason = {1:"A地址无应答", 2:"A-SCL低超时"}.get(info.get('fault'),
                       "B正常读" if c.reason == 6 else "A原因未记录")
            self.capture_list.insert("", "end", iid=f"{saved.session_number}:{c.capture_id}",
                                     text=f"{saved.session_number} / {c.capture_id}",
                                     values=(reason, len(c.samples)))
        status = snapshot.get("status", {})
        state = ("波形冻结/上传，协议监测继续" if status.get("frozen") else
                 "自动监测/滚动采样" if status.get("ready") else
                 "触发后采样，协议监测继续" if status else "等待设备状态")
        if snapshot.get("closed"):
            state = "接收已结束，归档已保存"
            self.connect_button.configure(state="normal")
        self.connection.set(state+"；"+snapshot.get("connection_error", ""))
        self.health.set(f"接收 {snapshot.get('bytes',0):,}B | CRC错 {snapshot.get('crc_errors',0)} | "
                        f"序号缺失 {snapshot.get('sequence_gaps',0)} | 抓拍忙时未保存 {status.get('missed_captures','待状态')} | "
                        f"队列丢失 {status.get('fifo_drops','待状态')} | 重组错 {snapshot.get('assembler_error_count',0)}")
        lines = []
        for record in snapshot.get("records", ())[-25:]:
            kind = record["kind"]
            if kind in (0x20, 0x21):
                label = "完整14字节" if record["full_read"] else "普通/不完整事务"
                lines.append(f"{'AB'[record['bus']]} 0x{record['address']:02X} {label}\n{record['data']}")
            elif kind == 0x32:
                lines.append(f"{fault_title(record)}\n关联#{record['correlation_id']} " +
                             ("地址ACK及时" if record["result"] == 1 else "地址ACK超时")+
                             f" {record['elapsed_ticks']*0.02:.2f}us")
            elif kind == 0x33:
                lines.append(f"读取#{record['correlation_id']} " +
                             {1:"完整读取成功",2:"读取不完整",3:"读取超时"}.get(record["result"],"未知"))
            elif kind in (0x30, 0x31):
                bus = 'A' if kind == 0x30 else 'B'
                lines.append(f"{fault_title(record, bus)}\n{fault_detail(record, bus)}")
        if snapshot.get("assembler_errors"):
            lines.extend(snapshot["assembler_errors"][-3:])
        self.records_text.delete("1.0", "end")
        self.records_text.insert("1.0", "\n\n".join(lines))
        self.draw()

    def show_decoded(self, snapshot):
        text = decoded_text(snapshot)
        if text == self._decoded_display:
            return
        position = self.decoded_text.yview()[0]
        self.decoded_text.configure(state='normal')
        self.decoded_text.delete('1.0', 'end')
        self.decoded_text.insert('1.0', text)
        self.decoded_text.configure(state='disabled')
        self.decoded_text.yview_moveto(position)
        self._decoded_display = text

    def diagnosis(self, saved):
        if saved.a_fault is not None:
            return saved.a_fault
        # 兼容旧调用方/旧归档；缓存识别结果，不在每100ms刷新时反复解码原始样点。
        c = saved.capture
        key = (saved.path, saved.session_number, c.capture_id, c.trigger_tick)
        if key not in self._diagnosis_cache:
            self._diagnosis_cache[key] = capture_fault(c, b_reads=saved.b_reads)
            if len(self._diagnosis_cache) > 64:
                self._diagnosis_cache.pop(next(iter(self._diagnosis_cache)))
        return self._diagnosis_cache[key]

    def draw(self):
        self.fault_view_status.set(fault_view_text(
            self.pinned, self.snapshot.get("latest_a_fault"), self.local_pin))
        if self.pinned:
            info = self.diagnosis(self.pinned)
            text = "本份异常："+fault_title(info)
            if info.get('normal'):
                text = "本份："+fault_title(info)
            else:
                text += "；"+backup_status(info)[0]
            self.fixed_fault_reason.set(text)
            self.fixed_reason_label.configure(foreground="#66717d" if info.get('normal') else "#b42318")
        else:
            self.fixed_fault_reason.set("本份异常原因：等待完整故障证据")
        for name, saved, channels, figure, canvas, label in (
            ("fault", self.pinned, (0,1,2,3), self.fault_figure, self.fault_canvas, self.fault_label),
            ("live", self.latest_b, (2,3), self.live_figure, self.live_canvas, self.live_label)):
            previous = getattr(self, "drawn_"+name)
            if previous is saved:
                continue
            if saved is None:
                # 从手动归档恢复自动模式时，可能还没有收到完整故障波形。
                # 此时要清掉旧图，不能只改成“等待”文字却留下旧的电平。
                self.navigation[name].clear()
                draw_waiting(figure, channels)
                canvas.draw_idle()
                setattr(self, "drawn_"+name, None)
                continue
            c = saved.capture
            title = f"会话{saved.session_number} / 捕获#{c.capture_id} / 原始波形 / {len(c.samples):,}点"
            if name == "live":
                title += f" / 完整B读取{len(saved.b_reads)}次"
            label.set(title)
            self.navigation[name].clear()
            draw_capture(figure, c, channels, title)
            self.navigation[name].set_capture(c)
            canvas.draw_idle()
            setattr(self, "drawn_"+name, saved)

    def show_full(self, name):
        self.navigation[name].show_full()

    def export(self):
        if not self.pinned or self.export_future and not self.export_future.done():
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv")
        if path:
            self.export_future = self.exports.submit(export_csv, self.pinned, path)
            self.connection.set("正在后台导出CSV，串口接收继续")

    def export_png(self):
        if self.pinned:
            path = filedialog.asksaveasfilename(defaultextension=".png")
            if path:
                # 已建立的Figure属于主线程；只导出当前固定图，不重算原始数据。
                self.fault_figure.savefig(path, dpi=160)

    def poll(self):
        if self.receiver:
            try:
                self.apply_snapshot(self.receiver.updates.get_nowait())
            except Empty:
                pass
        if self.export_future and self.export_future.done():
            error = self.export_future.exception()
            self.connection.set("CSV导出失败："+str(error) if error else "CSV导出完成")
            self.export_future = None
        self.root.after(100, self.poll)

    def close(self):
        self.disconnect()
        if self.receiver and self.receiver.processor.is_alive():
            self.connection.set("正在保存接收缓冲，完成后关闭窗口")
            self.root.after(100, self.close)
            return
        self.exports.shutdown(wait=False)
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay", help="离线串口流(.bin或仿真.hex)，不连接硬件")
    args = parser.parse_args()
    root = tk.Tk()
    app = Application(root)
    if args.replay:
        app._start(replay=args.replay)
    root.mainloop()


if __name__ == "__main__":
    main()
