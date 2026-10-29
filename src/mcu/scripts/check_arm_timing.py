"""检查旧ARMCC实际保留周期等待循环；不冒充运行速度或外部线形测试。"""
from pathlib import Path
import re
root=Path(__file__).resolve().parents[1]
text=(root/'verification/disassembly.txt').read_text(encoding='utf-8')
for name in ('FastPort_DelayUs','Send','FastI2C_ReadRegs','Start','Stop','Failover_Run'):
    body=text.split('    i.'+name+'\n',1)[1].split('    i.',1)[0]
    assert re.search(r'TST\s+[^\n]*0x80000000',body),name+' missing wrap-aware wait test'
    assert re.search(r'BNE\s+0x',body),name+' missing wait back branch'
print('PASS ARMCC wait loops present in DelayUs/Send/ReadRegs/Start/Stop/Failover_Run')
