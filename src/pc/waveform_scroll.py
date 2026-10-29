"""波形页面纵向滚动：保留波形高度，滚轮在坐标区内仍交给缩放。"""
import tkinter as tk
from tkinter import ttk


class WaveformScroll(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.viewport = tk.Canvas(self, width=1000, highlightthickness=0, yscrollincrement=24)
        scrollbar = ttk.Scrollbar(self, orient='vertical', command=self.viewport.yview)
        scrollbar.pack(side='right', fill='y')
        self.viewport.pack(side='left', fill='both', expand=True)
        self.viewport.configure(yscrollcommand=scrollbar.set)
        self.content = ttk.Frame(self.viewport)
        self.content_id = self.viewport.create_window(0, 0, window=self.content, anchor='nw')
        self.plots = []
        self.wheel_remainder = 0
        self.content.bind('<Configure>', self._content_changed)
        self.viewport.bind('<Configure>', self._viewport_changed)
        # 使用当前窗口的绑定，不影响右侧列表或其他应用的滚轮。
        self.winfo_toplevel().bind('<MouseWheel>', self._on_mousewheel, add='+')

    def register_plot(self, canvas):
        self.plots.append(canvas)

    def _content_changed(self, _event=None):
        self.viewport.configure(scrollregion=self.viewport.bbox('all'))

    def _viewport_changed(self, event):
        # 仅同步宽度；高度由两块波形的实际需要决定，窗口小就滚动查看。
        self.viewport.itemconfigure(self.content_id, width=event.width)

    def _on_mousewheel(self, event):
        hovered = self.winfo_containing(event.x_root, event.y_root)
        return self.route_wheel(hovered, event.x_root, event.y_root, event.delta)

    def route_wheel(self, hovered, x_root, y_root, delta):
        """按指针所在位置分配滚轮：通道内缩放，页面其他位置纵向滚动。"""
        widget = hovered
        while widget is not None and widget is not self:
            widget = widget.master
        if widget is None:
            return
        for canvas in self.plots:
            plot = canvas.get_tk_widget()
            if hovered is plot:
                x = plot.canvasx(x_root-plot.winfo_rootx())
                y = canvas.figure.bbox.height-plot.canvasy(y_root-plot.winfo_rooty())
                if canvas.inaxes((x, y)) is not None:
                    return  # 通道坐标区：后续由Matplotlib执行原有滚轮缩放。
        # 空白、标题、工具条区域：滚动页面；累积小滚轮增量以兼容触摸板。
        self.wheel_remainder -= delta/120
        steps = int(self.wheel_remainder)
        self.wheel_remainder -= steps
        if steps:
            self.viewport.yview_scroll(steps*2, 'units')
        return 'break'
