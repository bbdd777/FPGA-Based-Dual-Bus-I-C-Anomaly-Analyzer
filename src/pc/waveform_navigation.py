"""波形时间轴操作：滚轮缩放，左键拖动；各窗口独立、同窗通道同步。"""
from matplotlib.backend_bases import MouseButton


class WaveformNavigation:
    def __init__(self, canvas, toolbar):
        self.canvas = canvas
        self.toolbar = toolbar
        self.axes = ()
        self.full_limits = None
        self.minimum_width = 0
        self.drag = None
        # 只在创建画布时绑定一次；换波形只更新坐标轴，避免越用缩放越快。
        for name, callback in (
            ("scroll_event", self._on_scroll),
            ("button_press_event", self._on_press),
            ("motion_notify_event", self._on_motion),
            ("button_release_event", self._on_release),
            ("figure_leave_event", self._finish_drag),
        ):
            canvas.mpl_connect(name, callback)

    def clear(self):
        """换包时结束拖动、清空旧视图历史，防止后退到另一份波形的坐标。"""
        self._finish_drag()
        self.axes = ()
        self.full_limits = None
        self.toolbar.update()

    def set_capture(self, capture):
        self.clear()
        self.axes = tuple(self.canvas.figure.axes)
        # 横轴单位为微秒。默认图聚焦通信区，但允许缩小到完整采样范围。
        self.full_limits = (-capture.trigger_index * capture.period_ns / 1000,
                            (len(capture.samples)-capture.trigger_index) * capture.period_ns / 1000)
        full_width = self.full_limits[1]-self.full_limits[0]
        self.minimum_width = min(full_width, 10 * capture.period_ns / 1000)
        self.toolbar.push_current()

    def _can_handle(self, event):
        # 工具栏选中平移/框选时交给原工具，避免一次鼠标动作执行两遍。
        return (event.inaxes in self.axes and not self.toolbar.mode
                and not self.canvas.widgetlock.locked())

    def _set_limits(self, axis, left, width):
        """仅移动时间轴，范围不越过本份样点；数字电平的0/1纵轴保持不动。"""
        first, last = self.full_limits
        width = max(self.minimum_width, min(last-first, width))
        left = max(first, min(left, last-width))
        # 同一窗口的通道使用sharex，修改一路即可同步各路时间轴。
        axis.set_xlim(left, left+width)
        self.canvas.draw_idle()

    def _on_scroll(self, event):
        if not self._can_handle(event) or event.xdata is None or not event.step:
            return
        axis = event.inaxes
        left, right = axis.get_xlim()
        width = right-left
        full_width = self.full_limits[1]-self.full_limits[0]
        # 上滚放大、下滚缩小；最少显示10个样点，最多完整采样窗口。
        step = max(-5, min(5, event.step))
        new_width = max(self.minimum_width, min(full_width, width / 1.25**step))
        if new_width == width:
            return
        fraction = (event.xdata-left)/width
        self._set_limits(axis, event.xdata-fraction*new_width, new_width)
        self.toolbar.push_current()

    def _on_press(self, event):
        if event.button != MouseButton.LEFT or not self._can_handle(event):
            return
        # 用按下时的像素位置计算位移；不用变化中的xdata，避免拖动跳动。
        self.drag = (event.inaxes, event.x, event.inaxes.get_xlim())
        self.canvas.widgetlock(self)

    def _on_motion(self, event):
        if self.drag is None or event.x is None:
            return
        axis, start_x, (left, right) = self.drag
        shift = (start_x-event.x) * (right-left) / axis.bbox.width
        self._set_limits(axis, left+shift, right-left)

    def _on_release(self, event):
        if event.button == MouseButton.LEFT:
            self._finish_drag()

    def _finish_drag(self, event=None):
        # 松开或离开画布立即结束，避免返回波形区后仍跟着鼠标走。
        if self.drag is None:
            return
        axis, _, old_limits = self.drag
        self.drag = None
        self.canvas.widgetlock.release(self)
        if axis.get_xlim() != old_limits:
            self.toolbar.push_current()

    def show_full(self):
        if not self.axes:
            return
        self._finish_drag()
        first, last = self.full_limits
        self._set_limits(self.axes[0], first, last-first)
        self.toolbar.push_current()
