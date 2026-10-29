#include "failoverapp.h"
#include "fastport.h"
#include <string.h>
volatile Failover_Report LastReport;
volatile Failover_Report EventLog[APP_LOG_DEPTH];
volatile uint32_t EventLogCount;
static uint8_t InitStatus;
static Failover_Report Current;
static const char *Names[4]={"IDLE","NORMAL A+B","A NACK -> B","A SCL -> B"};
const char *Failover_Name(uint8_t Mode) { return Mode<4u?Names[Mode]:"INVALID"; }
uint8_t Failover_Init(void)
{
    memset(&Current,0,sizeof(Current));
    memset((void *)&LastReport,0,sizeof(LastReport));
    memset((void *)EventLog,0,sizeof(EventLog)); EventLogCount=0;
    Sensors_Reset(); InitStatus=FastI2C_Init();
    return InitStatus;
}
static void Backup(void)
{
    Current.BackupAttempted=1;
    (void)Sensors_Read(BUS_B,&Current.BData,&Current.BResult);
    Current.BackupAckValid=Current.BResult.AddressValid && !Current.BResult.AddressNack;
    if (Current.BackupAckValid) {
        uint32_t Delta=Current.BResult.AddressCycle-Current.FaultCycle;
        Current.BackupAckUs=Delta/FAST_CYCLES_US;
        /* 用周期数比较，不先截成us，防止1000.9us误判为1000us。 */
        Current.WithinWindow=(Delta<=1000u*FAST_CYCLES_US);
    }
    Current.BackupSuccess=Current.BData.Valid && Current.BResult.Status==I2C_OK;
    if (Current.BackupSuccess) {
        Current.Source=APP_SOURCE_B;
        Current.BackupReadUs=(Current.BResult.EndCycle-Current.FaultCycle)/FAST_CYCLES_US;
    }
}
uint8_t Failover_Run(uint8_t Mode)
{
    uint8_t PrepareB;
    uint32_t LowStart=0;
    if (Mode>=APP_MODE_COUNT || Current.Active) { return 0; }
    memset(&Current,0,sizeof(Current));
    Current.Mode=Mode; Current.Active=1; Current.Sequence=EventLogCount+1u;
    Current.AResult.Status=I2C_NOT_RUN; Current.BResult.Status=I2C_NOT_RUN;
    LastReport=Current;
    if (Mode==0u) {
        FastPort_Release(0); FastPort_Release(1);
    } else if (InitStatus) {
        Current.AResult.Status=InitStatus; Current.BResult.Status=InitStatus;
    } else {
        /* 备用设备提前就绪，不能在A故障后再阻塞100ms唤醒B。
         * 失败仍执行本轮并记录失败；不会把初始化失败伪装成备用读取成功。
         */
        PrepareB=Sensors_Prepare(BUS_B);
        if (Mode==1u) {
            (void)Sensors_Prepare(BUS_A);
            (void)Sensors_Read(BUS_A,&Current.AData,&Current.AResult);
            (void)Sensors_Read(BUS_B,&Current.BData,&Current.BResult);
            if (Current.AData.Valid) { Current.Source=APP_SOURCE_A; }
            else {
                Current.Fault=APP_FAULT_A_OTHER;
                Current.FaultCycle=Current.AResult.EndCycle;
                /* M1意外A故障也可由已读到的有效B接替，但不伪造精确切换计时。 */
                Current.BackupAttempted=1; Current.BackupSuccess=Current.BData.Valid;
                if (Current.BData.Valid) { Current.Source=APP_SOURCE_B; }
            }
        } else if (Mode==2u) {
            (void)FastI2C_Probe(BUS_A,0x6au,&Current.AResult);
            if (Current.AResult.Status==I2C_ADDRESS_NACK &&
                Current.AResult.AddressValid && Current.AResult.AddressNack) {
                Current.Fault=APP_FAULT_A_NACK;
                Current.FaultCycle=Current.AResult.AddressCycle;
            } else if (Current.AResult.Status!=I2C_OK) {
                Current.Fault=APP_FAULT_A_OTHER;
                Current.FaultCycle=Current.AResult.EndCycle;
            }
            /* 0x6A意外真实ACK时，不编造A故障、也不触发备用。 */
            if (Current.Fault) { Backup(); }
        } else {
            FastPort_HoldALow(1); LowStart=FastPort_Now();
            FastPort_WaitUntil(LowStart+500u*FAST_CYCLES_US);
            Current.Fault=APP_FAULT_A_SCL;
            /* 低500us才确认故障；B在A仍保持低时独立读取，不等A先恢复。 */
            Current.FaultCycle=FastPort_Now();
            Current.AResult.Status=I2C_INJECTED_LOW;
            Current.AResult.EndCycle=Current.FaultCycle;
            Backup();
            FastPort_WaitUntil(LowStart+1000u*FAST_CYCLES_US);
            FastPort_HoldALow(0);
            Current.LowHoldUs=(FastPort_Now()-LowStart)/FAST_CYCLES_US;
        }
        /* PrepareB只是预备结果；备用数据失败的具体原因在BResult中保留。 */
        (void)PrepareB;
    }
    Current.Active=0;
    EventLog[EventLogCount%APP_LOG_DEPTH]=Current;
    EventLogCount++; LastReport=Current;
    return 1;
}
