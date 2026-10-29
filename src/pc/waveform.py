"""原始样点分析与画图。画图保留每个边沿，不用隔N点抽取掩盖窄脉冲。"""
from dataclasses import dataclass
from matplotlib.transforms import Bbox, TransformedBbox


CHANNEL_LABELS = ("CH0 · A-SCL", "CH1 · A-SDA", "CH2 · B-SCL", "CH3 · B-SDA")


def layout_waveform(figure):
    """按画布尺寸留固定文字边距，不让缩放后的地址标注把通道挤扁。"""
    if not figure.axes:
        return
    width, height = figure.get_size_inches()*figure.dpi
    scale = figure.dpi/100
    left = min(145*scale, width*0.34)
    right = min(12*scale, width*0.04)
    top = min((25 if figure._suptitle else 12)*scale, height*0.15)
    bottom = min(44*scale, height*0.25)
    gap = min(12*scale, (height-top-bottom)/(len(figure.axes)*3))
    row_height = (height-top-bottom-gap*(len(figure.axes)-1))/len(figure.axes)
    figure.subplots_adjust(left=left/width, right=1-right/width,
                           top=1-top/height, bottom=bottom/height,
                           hspace=gap/max(1, row_height))
    if figure._suptitle:
        figure._suptitle.set_position((left/width, 1-3*scale/height))


def label_event(axis, x, y, text, **style):
    """横向跟随视窗裁切；纵向留出标注空间，不裁掉图上方的地址文字。"""
    label = axis.text(x, y, text, clip_on=True, **style)
    label.set_clip_path(None)
    label.set_clip_box(TransformedBbox(Bbox.from_extents(0, -10, 1, 10), axis.transAxes))
    label.set_in_layout(False)


def label_channel(axis, channel):
    """等待状态与实际波形共用同一通道编号，名称横向放在各行左侧。"""
    axis.set_ylabel(CHANNEL_LABELS[channel], rotation=0, ha="right", va="center",
                    labelpad=16, fontsize=10, fontweight="bold")
    axis.set_ylim(-0.2, 1.4)
    axis.set_yticks((0, 1))
    axis.grid(True, alpha=0.25)


def draw_waiting(figure, channels):
    """未接收数据也先显示通道位置；只画空坐标，不生成任何模拟波形。"""
    figure.clear()
    axes = figure.subplots(len(channels), 1, sharex=True, squeeze=False).ravel()
    for axis, channel in zip(axes, channels):
        label_channel(axis, channel)
        axis.set_xlim(0, 1)
        axis.set_xticks([])
        axis.text(0.5, 0.5, "等待原始采样数据", transform=axis.transAxes,
                  ha="center", va="center", color="#7a8491", fontsize=10)
    axes[-1].set_xlabel("尚无采样数据，接收后显示时间轴")
    layout_waveform(figure)
    return axes


@dataclass(frozen=True)
class Transaction:
    start_index: int
    stop_index: int
    addresses: tuple
    data: bytes
    acks: tuple
    full_read: bool


def decode_i2c(samples: bytes, bus=1):
    scl_mask, sda_mask = 1 << (bus*2), 2 << (bus*2)
    previous = samples[0] if samples else 15
    active = False
    addresses, data, acks = [], bytearray(), []
    bits, value, need_address = 0, 0, True
    start = 0
    pointer_ok = False
    read_ok = False
    result = []
    for index, sample in enumerate(samples[1:], 1):
        old_scl, scl = bool(previous & scl_mask), bool(sample & scl_mask)
        old_sda, sda = bool(previous & sda_mask), bool(sample & sda_mask)
        if old_scl and scl and old_sda != sda:
            if not sda:
                if not active:
                    start, addresses, data, acks = index, [], bytearray(), []
                    pointer_ok = read_ok = False
                else:
                    pointer_ok = addresses == [(0x68, 0, 0)] and data == b"\x3b" and acks == [0]
                    data, acks = bytearray(), []
                active, bits, value, need_address = True, 0, 0, True
            elif active:
                complete = (pointer_ok and read_ok and len(data) == 14
                            and acks == [0]*13 + [1])
                result.append(Transaction(start, index, tuple(addresses), bytes(data), tuple(acks), complete))
                active = False
        elif active and not old_scl and scl:
            if bits < 8:
                value = (value << 1) | int(sda)
                bits += 1
            else:
                if need_address:
                    addresses.append((value >> 1, value & 1, int(sda)))
                    read_ok = pointer_ok and value == 0xD1 and not sda
                    need_address = False
                else:
                    data.append(value)
                    acks.append(int(sda))
                bits, value = 0, 0
        previous = sample
    return result


def edge_points(capture, channel, left=0, right=None):
    right = len(capture.samples) if right is None else min(right, len(capture.samples))
    left = max(0, left)
    if right <= left:
        return [], []
    raw = capture.samples
    mask = 1 << channel
    indices = [left]
    values = [int(bool(raw[left] & mask))]
    previous = values[0]
    for index in range(left+1, right):
        value = int(bool(raw[index] & mask))
        if value != previous:
            indices.append(index)
            values.append(value)
            previous = value
    indices.append(right)
    values.append(previous)
    times = [(index-capture.trigger_index)*capture.period_ns/1000 for index in indices]
    return times, values


def draw_capture(figure, capture, channels=(0, 1, 2, 3), title="", markers=()):
    figure.clear()
    axes = figure.subplots(len(channels), 1, sharex=True, squeeze=False).ravel()
    activity = []
    for axis, channel in zip(axes, channels):
        times, values = edge_points(capture, channel)
        activity.extend(times[1:-1])
        axis.step(times, values, where="post", linewidth=0.9)
        label_channel(axis, channel)
        axis.axvline(0, color="#c43b32", linewidth=0.7)
        for tick, label in markers:
            x = (tick-capture.trigger_tick)*capture.period_ns/1000
            axis.axvline(x, color="#e09a27", linewidth=0.6)
            if axis is axes[0]:
                label_event(axis, x, 1.05, label, fontsize=8)
        if channel in (0, 2):
            for transaction in decode_i2c(capture.samples, channel//2)[:8]:
                x = (transaction.start_index-capture.trigger_index)*capture.period_ns/1000
                addresses = "/".join(f"{address:02X}{'R' if rw else 'W'} {'NACK' if nack else 'ACK'}"
                                     for address, rw, nack in transaction.addresses)
                # 缩放/拖动后，视窗外的地址标注不能覆盖左侧通道名称。
                label_event(axis, x, 1.12, addresses, fontsize=7, color="#185b55")
                if transaction.full_read:
                    stop = (transaction.stop_index-capture.trigger_index)*capture.period_ns/1000
                    axis.axvline(stop, color="#25945d", linestyle=":", linewidth=0.7)
    # 默认聚焦实际通信区间，完整样点仍保留；工具条可缩放，“全窗口”可还原全长。
    if activity and max(activity) > min(activity):
        margin = max(5, (max(activity)-min(activity))*0.05)
        axes[-1].set_xlim(min(activity)-margin, max(activity)+margin)
    axes[-1].set_xlabel("相对本次抓拍触发 / us（不同窗口时间原点独立）")
    # 捕获信息只显示一遍，用较小的左对齐标题给波形留出高度。
    figure.suptitle(title, fontsize=10, ha='left', va='top')
    layout_waveform(figure)
    return axes
