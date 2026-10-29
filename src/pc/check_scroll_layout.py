"""真实Tk滚动页面检查；只回放既有文件，不占串口。--preview保留窗口。"""
import argparse
import hashlib
import json
from pathlib import Path
import tkinter as tk
from matplotlib.backend_bases import MouseEvent

from app import Application
from session import Session
from waveform import layout_waveform


def wheel(page, canvas, x, y, delta):
    # 直接验证页面分流函数和Matplotlib回调；真实Windows输入另由预览实操核对。
    widget = canvas.get_tk_widget()
    result = page.route_wheel(widget, widget.winfo_rootx()+x, widget.winfo_rooty()+y, delta)
    if result != 'break':
        event = MouseEvent('scroll_event', canvas, x, canvas.figure.bbox.height-y, step=delta/120)
        canvas.callbacks.process('scroll_event', event)
    widget.update()


def wheel_in_axis(page, canvas, delta):
    axis = canvas.figure.axes[0]
    x, y = axis.transAxes.transform((0.5, 0.5))
    point = (int(x), int(canvas.figure.bbox.height-y))
    wheel(page, canvas, *point, delta)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preview', action='store_true')
    args = parser.parse_args()
    pc = Path(__file__).resolve().parent
    output = pc/'verification/layout_scroll_20261021_200836'
    output.mkdir(exist_ok=True)
    source = pc.parent/'data/hardware_20261021_164502/basic_scenes/serial.raw.bin'
    if source.exists():
        raw = source.read_bytes()
        source_type = 'Read-only replay of existing hardware UART stream'
    else:
        source = pc.parent/'vivado_prj/verification/sim/core_stream.hex'
        raw = bytes.fromhex(source.read_text())
        source_type = 'Replay of existing RTL simulation UART stream'
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    session = Session()
    session.feed(raw)
    assert session.pinned and session.latest_b
    root = tk.Tk()
    root.withdraw()
    app = Application(root)
    root.title('FPGA 波形滚动布局预览（离线回放）')
    app.port.set('离线回放')
    app.connect_button.configure(state='disabled')
    app.apply_snapshot(session.snapshot())
    root.deiconify()
    root.update()
    original_geometry = root.geometry()
    checks = []
    for width, height in ((1440, 780), (1120, 680)):
        root.geometry(f'{width}x{height}')
        root.update()
        page = app.plot_scroll.viewport
        page.yview_moveto(0)
        root.update()
        upper = [a.bbox.height for a in app.fault_figure.axes]
        lower = [a.bbox.height for a in app.live_figure.axes]
        assert min(upper+lower) >= 35
        assert 0.7 < upper[0]/lower[0] < 1.3
        assert app.plot_scroll.content.winfo_height() > page.winfo_height()
        # 检验分流函数与回调：坐标区缩放，空白滚页面；原生输入在预览中另测。
        limits = app.fault_figure.axes[0].get_xlim()
        page_before = page.yview()
        wheel_in_axis(app.plot_scroll, app.fault_canvas, 120)
        zoomed = app.fault_figure.axes[0].get_xlim()
        assert zoomed[1]-zoomed[0] < limits[1]-limits[0]
        assert page.yview() == page_before
        wheel(app.plot_scroll, app.fault_canvas, 5, 5, -240)
        assert page.yview()[0] > page_before[0]
        assert app.fault_figure.axes[0].get_xlim() == zoomed
        # 最底部能够完整查看B；滚轮操作B不改变固定故障图。
        page.yview_moveto(1)
        root.update()
        live_limits = app.live_figure.axes[0].get_xlim()
        page_before = page.yview()
        wheel_in_axis(app.plot_scroll, app.live_canvas, 120)
        live_zoomed = app.live_figure.axes[0].get_xlim()
        assert live_zoomed[1]-live_zoomed[0] < live_limits[1]-live_limits[0]
        assert app.fault_figure.axes[0].get_xlim() == zoomed
        assert page.yview() == page_before
        # 改变横轴后反复重排，行高/位置不能随视窗内外的地址文字变化。
        positions = [a.get_position().bounds for a in app.fault_figure.axes]
        for _ in range(5):
            layout_waveform(app.fault_figure)
            app.fault_canvas.draw()
        assert positions == [a.get_position().bounds for a in app.fault_figure.axes]
        assert app.fault_figure.axes[0].get_xlim() == zoomed
        checks.append(dict(window=[width, height], upper_row_pixels=upper,
                           lower_row_pixels=lower, content_height=app.plot_scroll.content.winfo_height(),
                           viewport_height=page.winfo_height()))
    root.geometry(original_geometry)
    app.navigation['fault'].toolbar.home()
    app.navigation['live'].toolbar.home()
    app.plot_scroll.viewport.yview_moveto(0)
    app.connection.set('离线布局预览：波形上滚轮缩放，空白处滚页面；右侧滚动条可上下查看')
    root.update()
    app.fault_figure.savefig(output/'fault_layout.png', dpi=130)
    app.live_figure.savefig(output/'live_layout.png', dpi=130)
    assert source_sha == hashlib.sha256(source.read_bytes()).hexdigest()
    report = dict(passed=True, serial_opened=False, source=source_type, source_sha256=source_sha,
                  checks=checks, scroll_page_on_blank=True, zoom_on_axes=True,
                  fixed_view_retained=True, row_height_stable_after_zoom=True,
                  original_hardware_file_unchanged=True,
                  wheel_check_method='Page routing function and Matplotlib callbacks; native input checked separately')
    (output/'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)
    session.close()
    if args.preview:
        def stop_preview():
            if (output/'preview_close.request').exists():
                app.close()
            else:
                root.after(500, stop_preview)
        root.after(500, stop_preview)
        root.mainloop()
    else:
        app.close()


if __name__ == '__main__':
    main()
