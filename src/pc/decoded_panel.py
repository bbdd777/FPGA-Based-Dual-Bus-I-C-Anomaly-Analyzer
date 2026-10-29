"""A/B监听译码文字。只显示实收字节，原始量按大端有符号16位解释。"""
import struct
from faults import fault_title


def sensor_values(record):
    if (not record or not record.get('full_read') or record.get('count') != 14
            or record.get('pointer') != 0x3B):
        return None
    raw = bytes.fromhex(record.get('data', ''))
    if len(raw) != 14 or record.get('flags', 0) & 1:
        return None
    return dict(zip(('AX', 'AY', 'AZ', 'TEMP', 'GX', 'GY', 'GZ'), struct.unpack('>7h', raw)))


def decoded_text(snapshot):
    summaries = snapshot.get('latest_summary', {})
    valid_reads = snapshot.get('latest_sensor_summary', {})
    faults = snapshot.get('latest_bus_fault', {})
    lines = ['实时监听译码（与左侧固定波形独立）']
    for bus, name in enumerate(('A · MPU6050', 'B · MPU6500')):
        record = summaries.get(bus)
        valid = valid_reads.get(bus)
        fault = faults.get(bus)
        lines.extend(('', f'【设备{name}】'))
        if record:
            state = ('完整14字节读取' if sensor_values(record) is not None else
                     '异常/不完整事务' if record.get('flags', 0) & 1 else '普通事务')
            direction = '读' if record.get('rw') else '写'
            lines.append(f"最近事务：0x{record['address']:02X} {direction}，{record['count']}字节")
            lines.append(f"寄存器指针：0x{record['pointer']:02X}；{state}")
            lines.append(f"会话{record.get('session_number', 0)} / 帧{record.get('sequence', '?')}")
            if record.get('data'):
                lines.append('事务HEX：'+record['data'].upper())
        else:
            lines.append('尚未收到该设备事务')
        if fault and (not record or fault['tick'] >= record.get('start_tick', record.get('tick', 0))):
            lines.append('异常记录：'+fault_title(fault, 'AB'[bus]))
        # 后续失败或普通写事务不能清掉先前完整读数，但必须明确标记其来源。
        valid = valid or (record if sensor_values(record) is not None else None)
        values = sensor_values(valid)
        if values is None:
            lines.append('尚无有效的0x3B起始14字节读数')
            continue
        label = '本次完整读数' if record is valid or record == valid else '上次有效读数（非当前事务）'
        lines.append(label+f"：帧{valid.get('sequence', '?')}")
        raw = bytes.fromhex(valid['data'])
        lines.append('HEX：'+raw[:7].hex(' ').upper())
        lines.append('     '+raw[7:].hex(' ').upper())
        lines.append(f"加速度 AX={values['AX']}  AY={values['AY']}")
        lines.append(f"       AZ={values['AZ']}")
        lines.append(f"温度   TEMP={values['TEMP']}")
        lines.append(f"角速度 GX={values['GX']}  GY={values['GY']}")
        lines.append(f"       GZ={values['GZ']}")
    lines.extend(('', '数值为有符号原始量，未换算g、℃或°/s。',
                  '完整读末字节NACK属于正常结束。'))
    return '\n'.join(lines)
