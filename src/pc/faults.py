"""把已检测到的数字总线异常转成中文，不推断器件损坏或具体电气根因。"""
from waveform import decode_i2c


def with_receipt(info, record):
    """同一故障的后续关联/读结果不得把首次电脑接收时间刷新成较晚时刻。"""
    order = record.get('host_received_order')
    old_order = info.get('host_received_order')
    if record.get('host_received_at') and (not info.get('host_received_at')
            or order is not None and old_order is not None and order < old_order):
        info.update({key: record[key] for key in ('host_received_at', 'host_received_order', 'input_mode')
                     if key in record})
    return info


def receipt_text(info):
    if not info:
        return '电脑接收时间：等待异常'
    timestamp = info.get('host_received_at')
    if not timestamp:
        return '电脑接收时间：未记录'
    label = {'live': '电脑接收时间', 'replay': '回放接收时间', 'import': '导入识别时间'}.get(
        info.get('input_mode'), '电脑接收时间')
    return label+'：'+timestamp.replace('T', ' ')


def fault_view_text(saved, recent, manual=False):
    """说明当前图属于哪次捕获，避免事件先到、波形还在上传时误认旧图。"""
    if saved is None:
        return '自动跟随：等待完整故障原始波形（上传并校验完成后显示）'
    capture = saved.capture
    identity = f'会话{saved.session_number} / 捕获#{capture.capture_id}'
    if manual:
        return f'手动固定：{identity}；点击“跟随最新故障”恢复自动更新'
    if recent:
        same_session = saved.session_number == recent.get('session_number')
        # 优先按关联号对应；原始异常帧可能先到，尚无关联号时按异常源tick对应。
        correlation_id = recent.get('correlation_id')
        if correlation_id:
            same_fault = capture.correlation_id == correlation_id
        else:
            same_fault = (saved.a_fault or {}).get('tick') == recent.get('tick')
        if not (same_session and same_fault):
            return f'自动跟随：暂显示{identity}；最新异常尚无对应完整波形'
    return f'自动跟随最新完整故障：{identity}'


def update_a_fault(current, record, config):
    """仅把同一会话、同一故障的B应答/读结果关联起来，普通B更新不清故障。"""
    kind = record['kind']
    period = config.get('period_ns', 20)
    if kind == 0x11:
        return None  # FPGA重启后，最近事件重新开始；历史固定波形仍可保留。
    if (current and record.get('session_number', current['session_number']) < current['session_number']):
        return current
    if kind == 0x30:
        if (current and current['session_number'] == record['session_number']
                and current['tick'] > record['tick']):
            return current
        same = (current and current['session_number'] == record['session_number']
                and current['tick'] == record['tick'])
        result = dict(current) if same else {}
        result.update(fault=record['fault'], address=record.get('address'), tick=record['tick'],
                      session_number=record['session_number'],
                      low_us=config.get('low_ticks', 0)*period/1000 or None, source='event')
        return with_receipt(result, record)
    if kind == 0x32:
        if (current and current['session_number'] == record['session_number']
                and current['tick'] > record['start_tick']):
            return current  # 迟到的旧关联结果不能改写更新的A异常。
        same = (current and current['session_number'] == record['session_number']
                and current['tick'] == record['start_tick'])
        result = dict(current) if same else dict(address=None, source='event')
        result.update(fault=record['fault'], tick=record['start_tick'],
                      session_number=record['session_number'], correlation_id=record['correlation_id'],
                      ack_result=record['result'], ack_us=record['elapsed_ticks']*period/1000,
                      low_us=config.get('low_ticks', 0)*period/1000 or None)
        return with_receipt(result, record)
    if (kind == 0x33 and current
            and current.get('correlation_id') == record['correlation_id']
            and current['session_number'] == record['session_number']):
        return dict(current, read_result=record['result'])
    return current


def capture_fault(capture, records=(), config=None, b_reads=(), session_number=0):
    """优先用本份关联ID的事件；老归档没有事件时，从本份原始样点识别。

    这里只在完整归档生成/打开时运行，不在每次界面刷新时扫描262144点。
    识别不出来时明确写未知，不能仅凭“原因5=切换证据”猜NACK还是低超时。
    """
    if capture.reason not in (4, 5):
        return dict(fault=0, normal=True, source='capture')
    info = None
    linked = [r for r in records if r.get('session_number') == session_number
              and r.get('correlation_id') == capture.correlation_id and capture.correlation_id]
    correlation = next((r for r in linked if r['kind'] == 0x32), None)
    if correlation:
        fault = next((r for r in records if r['kind'] == 0x30
                      and r.get('session_number') == session_number
                      and r['tick'] == correlation['start_tick']), None)
        if fault:
            info = update_a_fault(None, fault, config or {})
        info = update_a_fault(info, correlation, config or {})
        for record in linked:
            if record['kind'] == 0x33:
                info = update_a_fault(info, record, config or {})
    if info is None:
        nacks = [address for transaction in decode_i2c(capture.samples, 0)
                 for address, _rw, nack in transaction.addresses if nack]
        longest = count = 0
        for value in capture.samples:
            count = count+1 if not value & 1 else 0
            longest = max(longest, count)
        low_us = (config or {}).get('low_ticks', 0)*capture.period_ns/1000 or 500
        low = longest*capture.period_ns/1000 >= low_us
        # 同窗包含两种异常但无关联记录时，不擅自选择其中一种作为触发原因。
        fault = 1 if nacks and not low else 2 if low and not nacks else 0
        info = dict(fault=fault, address=nacks[-1] if fault == 1 else None,
                    source='waveform', low_us=None, observed_low_us=longest*capture.period_ns/1000,
                    ack_result=2 if capture.reason == 4 else 1)
    return dict(info, b_full_read=bool(b_reads))


def fault_title(info, bus='A'):
    fault = info.get('fault', 0) if info else 0
    if fault == 1:
        return f'{bus} 地址无应答（NACK）'
    if fault == 2:
        return f'{bus} SCL持续低电平超时'
    if info and info.get('normal'):
        return '正常B读取抓拍，未关联A异常'
    return f'{bus} 异常原因未记录'


def fault_detail(info, bus='A'):
    if not info:
        return '收到A异常事件后显示检测原因和B接替结果。'
    if info.get('fault') == 1:
        address = info.get('address')
        target = f'地址0x{address:02X}' if isinstance(address, int) and 0 <= address <= 127 else '地址阶段'
        detail = f'{target}未收到从机应答，第9位为NACK。'
    elif info.get('fault') == 2:
        limit = info.get('low_us')
        detail = (f'{bus}的SCL连续保持低电平达到{limit:g} μs阈值。' if limit
                  else f'本份波形可见{bus}的SCL持续低电平。' if info.get('source') == 'waveform'
                  else f'{bus}的SCL持续低电平已触发超时。')
    else:
        detail = '当前证据不足以区分地址NACK和SCL低超时。'
    if info.get('source') == 'waveform':
        detail += ' 原因由本份原始样点识别。'
    if 'session_number' in info:
        detail += f" 会话{info['session_number']}"
        if info.get('correlation_id'):
            detail += f" / 关联#{info['correlation_id']}"
    return detail


def backup_status(info):
    """地址ACK仅表示应答及时；完整14字节成功必须单独确认。"""
    if not info:
        return 'B接替结果：等待异常事件', '#66717d'
    if info.get('ack_result') == 2:
        elapsed = info.get('ack_us')
        suffix = f'（{elapsed:.2f} μs）' if elapsed is not None else ''
        return 'B接替失败：地址应答超时'+suffix, '#b42318'
    result = info.get('read_result')
    if result == 1:
        return 'B接替成功：14字节完整读取', '#157347'
    if result in (2, 3):
        return ('B已应答，但读取不完整' if result == 2 else 'B已应答，但完整读取超时'), '#b42318'
    if info.get('ack_result') == 1:
        if info.get('b_full_read'):
            return 'B已应答；本份波形含完整14字节', '#157347'
        return 'B地址已应答，等待完整读取', '#9a6700'
    return 'B接替：等待地址应答', '#9a6700'
