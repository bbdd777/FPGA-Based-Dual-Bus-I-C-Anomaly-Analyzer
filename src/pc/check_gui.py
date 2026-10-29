"""离线构建真实Tk窗口，更新两个独立波形，确认固定视图对象不被替换。"""
from pathlib import Path
import json
import math
import tkinter as tk
from matplotlib.backend_bases import MouseEvent, MouseButton
from app import Application
from session import Session
from waveform import CHANNEL_LABELS


def mouse_event(canvas, name, axis, fraction=0.5, step=0, button=None, dx=0):
    """通过画布的真实回调入口操作，不绕过滚轮/按键绑定直接改坐标。"""
    x, y = axis.transAxes.transform((fraction, 0.5))
    event = MouseEvent(name, canvas, x+dx, y, button=button, step=step)
    canvas.callbacks.process(name, event)
    return event


def check_zoom_drag(app, name):
    canvas = app.fault_canvas if name == 'fault' else app.live_canvas
    canvas.draw()
    axes = canvas.figure.axes
    axis = axes[0]
    old_left, old_right = axis.get_xlim()
    old_y = [a.get_ylim() for a in axes]
    anchor = mouse_event(canvas, 'scroll_event', axis, fraction=0.4, step=2).xdata
    left, right = axis.get_xlim()
    assert math.isclose(right-left, (old_right-old_left)/1.25**2)
    assert math.isclose((anchor-left)/(right-left), (anchor-old_left)/(old_right-old_left))
    for a in axes:
        assert a.get_xlim() == axis.get_xlim()
    # 直接左键拖动，宽度不变，按像素位移换算为时间位移。
    press = mouse_event(canvas, 'button_press_event', axis, button=MouseButton.LEFT)
    moved = mouse_event(canvas, 'motion_notify_event', axis, dx=40)
    mouse_event(canvas, 'button_release_event', axis, dx=40, button=MouseButton.LEFT)
    first, last = app.navigation[name].full_limits
    expected = max(first, min(left+(press.x-moved.x)*(right-left)/axis.bbox.width,
                              last-(right-left)))
    assert math.isclose(axis.get_xlim()[0], expected)
    assert math.isclose(axis.get_xlim()[1]-axis.get_xlim()[0], right-left)
    assert [a.get_ylim() for a in axes] == old_y
    assert app.navigation[name].drag is None and not canvas.widgetlock.locked()
    return axis.get_xlim()


def check_navigation_bounds(app):
    canvas = app.fault_canvas
    nav = app.navigation['fault']
    axis = canvas.figure.axes[0]
    # 工具条后退/前进仍能恢复自定义鼠标操作的视图。
    current = axis.get_xlim()
    nav.toolbar.back()
    assert axis.get_xlim() != current
    nav.toolbar.forward()
    assert axis.get_xlim() == current
    # 工具条的平移模式有独立鼠标处理，直接滚轮不能与它叠加执行。
    nav.toolbar.pan()
    mouse_event(canvas, 'scroll_event', axis, step=1)
    assert axis.get_xlim() == current
    nav.toolbar.pan()
    # 连续放大到10个样点后不再缩小；缩小最终恰好到完整采样范围。
    for _ in range(15):
        mouse_event(canvas, 'scroll_event', axis, step=5)
    assert math.isclose(axis.get_xlim()[1]-axis.get_xlim()[0], nav.minimum_width)
    for _ in range(15):
        mouse_event(canvas, 'scroll_event', axis, step=-5)
    assert axis.get_xlim() == nav.full_limits
    # 移出画布结束拖动，之后的移动事件不会粘住视图。
    mouse_event(canvas, 'scroll_event', axis, step=3)
    mouse_event(canvas, 'button_press_event', axis, button=MouseButton.LEFT)
    canvas.callbacks.process('figure_leave_event', MouseEvent('figure_leave_event', canvas, -1, -1))
    stopped = axis.get_xlim()
    mouse_event(canvas, 'motion_notify_event', axis, dx=70)
    assert axis.get_xlim() == stopped and nav.drag is None and not canvas.widgetlock.locked()
    # 右键不启动拖动；空白处滚轮无效；完整窗口按钮允许再滚轮放大。
    mouse_event(canvas, 'button_press_event', axis, button=MouseButton.RIGHT)
    assert nav.drag is None
    canvas.callbacks.process('scroll_event', MouseEvent('scroll_event', canvas, -1, -1, step=1))
    assert axis.get_xlim() == stopped
    app.show_full('fault')
    assert axis.get_xlim() == nav.full_limits
    mouse_event(canvas, 'scroll_event', axis, step=1)
    assert axis.get_xlim()[1]-axis.get_xlim()[0] < nav.full_limits[1]-nav.full_limits[0]


def main():
    root_dir = Path(__file__).resolve().parent
    raw = bytes.fromhex((root_dir.parent / "vivado_prj/verification/sim/core_stream.hex").read_text())
    session = Session()
    root = tk.Tk()
    root.withdraw()
    app = Application(root)
    output = root_dir / "verification"
    output.mkdir(exist_ok=True)
    # 启动后没有任何样点，也必须能看到六个对应位置，且不画虚构的高低电平。
    assert [axis.get_ylabel() for axis in app.fault_figure.axes] == list(CHANNEL_LABELS)
    assert [axis.get_ylabel() for axis in app.live_figure.axes] == list(CHANNEL_LABELS[2:])
    assert not any(axis.lines for axis in app.fault_figure.axes+app.live_figure.axes)
    assert app.a_fault_title.get() == '尚未收到A异常'
    assert '等待异常' in app.a_fault_received.get()
    assert '设备A' in app.decoded_text.get('1.0', 'end')
    assert '设备B' in app.decoded_text.get('1.0', 'end')
    assert 'AX=' not in app.decoded_text.get('1.0', 'end')
    mouse_event(app.fault_canvas, 'scroll_event', app.fault_figure.axes[0], step=1)
    assert app.navigation['fault'].full_limits is None
    app.fault_canvas.draw()
    app.live_canvas.draw()
    app.fault_figure.savefig(output / "waiting_fault_channels.png", dpi=130)
    app.live_figure.savefig(output / "waiting_b_channels.png", dpi=130)
    first = None
    first_axes = None
    fixed_limits = None
    for offset in range(0, len(raw), 4096):
        session.feed(raw[offset:offset+4096])
        if session.captures:
            app.apply_snapshot(session.snapshot())
            root.update_idletasks()
            if first is None:
                first = app.pinned
                first_axes = tuple(app.fault_figure.axes)
                fixed_limits = check_zoom_drag(app, 'fault')
                assert '自动跟随最新完整故障' in app.fault_view_status.get()
                # 用户双击历史后才进入固定模式；后续B更新和新故障均保留此视图。
                app.capture_list.selection_set(f'{first.session_number}:{first.capture.capture_id}')
                app.select_pin()
                assert app.local_pin and '手动固定' in app.fault_view_status.get()
            assert app.pinned is first
            assert tuple(app.fault_figure.axes) == first_axes
            assert app.fault_figure.axes[0].get_xlim() == fixed_limits
    app.fault_canvas.draw()
    app.live_canvas.draw()
    assert app.pinned.capture.capture_id == 1
    assert app.latest_b.capture.capture_id == 3
    assert '导入识别时间' in app.a_fault_received.get()
    received_display = app.a_fault_received.get()
    app.apply_snapshot(session.snapshot())
    assert app.a_fault_received.get() == received_display
    decoded = app.decoded_text.get('1.0', 'end')
    assert 'AX=' in decoded and 'TEMP=' in decoded and 'GX=' in decoded
    assert app.decoded_text.cget('state') == 'disabled'
    check_zoom_drag(app, 'live')
    assert app.fault_figure.axes[0].get_xlim() == fixed_limits
    check_navigation_bounds(app)
    assert 'SCL' in app.a_fault_title.get()
    assert 'NACK' in app.fixed_fault_reason.get()
    assert '14字节完整读取' in app.backup_result.get()
    assert [app.capture_list.item(key, 'values')[0] for key in app.capture_list.get_children()] == [
        'A地址无应答', 'B正常读', 'A-SCL低超时']
    # 手动选择与自动跟随明确区分；恢复时立刻转到最新完整低超时证据。
    app.pinned = session.captures[-1]
    app.local_pin = True
    app.draw()
    assert 'SCL' in app.fixed_fault_reason.get()
    app.auto_pin()
    assert app.pinned is session.latest_fault and app.pinned.capture.capture_id == 3
    assert 'SCL' in app.fixed_fault_reason.get() and 'SCL' in app.a_fault_title.get()
    assert not app.local_pin and '自动跟随最新完整故障' in app.fault_view_status.get()
    # 切换归档后绑定新坐标，各窗口仍可操作，旧图不留拖动锁。
    check_zoom_drag(app, 'fault')
    assert len(app.fault_figure.axes) == 4 and len(app.live_figure.axes) == 2
    assert [axis.get_ylabel() for axis in app.fault_figure.axes] == list(CHANNEL_LABELS)
    assert [axis.get_ylabel() for axis in app.live_figure.axes] == list(CHANNEL_LABELS[2:])
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)
    assert not any("布防" in str(w.cget("text")) or "ARM" in str(w.cget("text"))
                   for w in descendants(root) if w.winfo_class() == "TButton")
    app.fault_figure.savefig(output / "fixed_fault.png", dpi=130)
    app.live_figure.savefig(output / "latest_b.png", dpi=130)
    result = dict(passed=True, manual_fixed_capture=1, auto_fault_capture=3, latest_capture=3,
                  fixed_axes_retained=True,
                  fault_channels=4, live_channels=2, serial_opened=False,
                  channel_labels_visible_before_data=True, empty_view_has_no_waveform=True)
    result.update(recent_low_timeout_visible=True, pinned_nack_reason_retained=True,
                  capture_list_has_actual_fault_types=True, backup_complete_read_separate=True)
    result.update(scroll_zoom_and_left_drag_both_views=True, zoom_anchored_at_pointer=True,
                  shared_time_axes=True, fixed_view_retained_during_live_updates=True,
                  actual_sample_bounds_and_minimum_zoom=True, toolbar_history_compatible=True,
                  no_sticky_drag_after_leave=True, navigation_after_capture_switch=True)
    result.update(decoded_devices_visible=True, sensor_raw_visible=True, decoded_panel_readonly=True)
    result.update(fault_receipt_clock_visible=True, receipt_not_changed_by_ui_refresh=True)
    result.update(auto_follows_latest_complete_fault=True, manual_mode_visible=True,
                  resume_auto_uses_latest_fault=True)
    # 手动开过图，但当前会话还没有完整故障时，恢复自动应显示空坐标。
    app.snapshot = {}
    app.auto_pin()
    assert app.pinned is None and not any(axis.lines for axis in app.fault_figure.axes)
    assert '等待完整故障' in app.fault_view_status.get()
    result.update(resume_without_capture_clears_old_wave=True)
    (output / "gui_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    app.close()


if __name__ == "__main__":
    main()
