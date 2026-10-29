#include "fasti2c.h"
#include "fastport.h"
#include <string.h>

/* Fast-mode目标400kHz：72MHz/180=400000。低96拍=1.333us，
 * 剩余84拍=1.167us；满足低>=1.3us、高>=0.6us的数字时序目标。
 * 采用绝对截止时间，不把循环次数当微秒。编译执行及GPIO延迟仍须上板测量；
 * 绝不能仅用180这个常数宣称实测400kHz。SCL拉伸时自动延长高电平起点。
 * 一字节临界区屏蔽中断约22.5us，字节之间恢复，避免OLED/按键拉长位周期。
 */
#define PERIOD_CYCLES 180u
#define LOW_CYCLES 96u
#define HIGH_MIN_CYCLES 44u
#define START_HOLD_CYCLES 48u
#define SCL_TIMEOUT_CYCLES (500u*FAST_CYCLES_US)
static uint8_t Ready;
static uint32_t FallCycle;
static uint32_t ActualFallCycle;
volatile FastI2C_Clock LastByteClocks[2][9];

FAST_INLINE void Fall(uint8_t Bus)
{
    FastPort_Clear(FAST_SCL_PINS(Bus));
    FallCycle=FastPort_Now();
    ActualFallCycle=FallCycle;
}
FAST_INLINE uint8_t Rise(uint32_t Scl,uint32_t *RiseCycle)
{
    uint32_t Deadline;
    FastPort_Set(Scl);
    /* 健康总线先快速读高；仅真实拉伸时才建立500us慢路径，
     * 避免每个位都为不会发生的超时计算浪费高电平预算。 */
    if (FastPort_Read()&Scl) {
        *RiseCycle=FastPort_Now();
        return I2C_OK;
    }
    Deadline=FastPort_Now()+SCL_TIMEOUT_CYCLES;
    while (!(FastPort_Read()&Scl)) {
        if ((int32_t)(FastPort_Now()-Deadline)>=0) { return I2C_SCL_TIMEOUT; }
    }
    *RiseCycle=FastPort_Now();
    return I2C_OK;
}
static uint8_t Start(uint8_t Bus,uint8_t Repeated)
{
    uint32_t RiseCycle;
    uint8_t Error;
    FastPort_Set(FAST_SDA_PINS(Bus));
    FastPort_WaitUntil(FallCycle+LOW_CYCLES);
    Error=Rise(FAST_SCL_PINS(Bus),&RiseCycle);
    if (Error) { return Error; }
    FastPort_WaitUntil(RiseCycle+START_HOLD_CYCLES);
    if (!(FastPort_Read()&FAST_SDA_PINS(Bus))) { return I2C_BUS_BUSY; }
    if (!Repeated) { FastPort_WaitUntil(RiseCycle+LOW_CYCLES); }
    FastPort_Clear(FAST_SDA_PINS(Bus));
    FastPort_WaitUntil(FastPort_Now()+START_HOLD_CYCLES);
    Fall(Bus);
    return I2C_OK;
}
static uint8_t Stop(uint8_t Bus)
{
    uint32_t RiseCycle;
    uint8_t Error;
    Fall(Bus);
    FastPort_Clear(FAST_SDA_PINS(Bus));
    FastPort_WaitUntil(FallCycle+LOW_CYCLES);
    Error=Rise(FAST_SCL_PINS(Bus),&RiseCycle);
    if (!Error) {
        FastPort_WaitUntil(RiseCycle+START_HOLD_CYCLES);
        FastPort_Set(FAST_SDA_PINS(Bus));
        FastPort_WaitUntil(FastPort_Now()+LOW_CYCLES);
        if (!(FastPort_Read()&FAST_SDA_PINS(Bus))) { Error=I2C_BUS_BUSY; }
    }
    FastPort_Release(Bus);
    return Error;
}

/* 一个数据位或应答位。SDA释放后才读：从机必须真实驱动ACK/数据。
 * 末字节由主机主动发送NACK，ReadRegs不把这个正常读结束当成故障。
 */
FAST_INLINE uint8_t Bit(uint32_t Scl,uint32_t Sda,uint8_t Release,uint8_t *Read,uint32_t *Edge)
{
    uint32_t RiseCycle,End;
    uint8_t Error;
    if (Release) { FastPort_Set(Sda); }
    else { FastPort_Clear(Sda); }
    FastPort_WaitUntil(FallCycle+LOW_CYCLES);
    Error=Rise(Scl,&RiseCycle);
    if (Error) { return Error; }
    *Edge=RiseCycle;
    /* 从机在SCL低阶段已准备数据，读到SCL高后即可采样。
     * 高电平最短保持由下面End截止保证，不用先等到末尾才读。 */
    *Read=(FastPort_Read()&Sda)?1u:0u;
    End=FallCycle+PERIOD_CYCLES;
    /* 拉伸/执行延迟可能使原定截止太早；至少保证真实读高后0.611us。 */
    if ((int32_t)(End-(RiseCycle+HIGH_MIN_CYCLES))<0) {
        End=RiseCycle+HIGH_MIN_CYCLES;
    }
    FastPort_WaitUntil(End);
    FastPort_Clear(Scl);
    ActualFallCycle=FastPort_Now();
    /* 下一位沿用计划截止，不在每个位加上GPIO/取样指令耗时。
     * 实际下降沿另记，用于真实周期观测。拉伸导致的延长已并入End。
     */
    FallCycle=End;
    return I2C_OK;
}
static uint8_t Send(uint8_t Bus,uint8_t Byte,uint8_t IsAddress,
                    FastI2C_Result *Result)
{
    uint8_t Index,Value,Error=0;
    FastI2C_Clock Clocks[9];
    uint32_t Previous;
    uint32_t Scl=FAST_SCL_PINS(Bus),Sda=FAST_SDA_PINS(Bus);
    uint32_t Edge=0,Saved=FastPort_Lock();
    for (Index=0;Index<8u;Index++) {
        Previous=ActualFallCycle;
        Error=Bit(Scl,Sda,(Byte&0x80u)?1u:0u,&Value,&Edge);
        Clocks[Index].Period=ActualFallCycle-Previous;
        Clocks[Index].LowObserved=Edge-Previous;
        if (Error) { break; }
        Byte=(uint8_t)(Byte<<1);
    }
    if (!Error) {
        Previous=ActualFallCycle;
        Error=Bit(Scl,Sda,1,&Value,&Edge);
        Clocks[8].Period=ActualFallCycle-Previous;
        Clocks[8].LowObserved=Edge-Previous;
        if (!Error) {
            if (IsAddress && !Result->AddressValid) {
                Result->AddressValid=1; Result->AddressNack=Value;
                Result->AddressCycle=Edge;
            }
            if (Value) { Error=IsAddress?I2C_ADDRESS_NACK:I2C_DATA_NACK; }
        }
    }
    FastPort_Unlock(Saved);
    if (Index==8u && (Error==I2C_OK || Error==I2C_ADDRESS_NACK || Error==I2C_DATA_NACK)) {
        memcpy((void *)LastByteClocks[Bus],Clocks,sizeof(Clocks));
    }
    return Error;
}
static uint8_t Receive(uint8_t Bus,uint8_t *Byte,uint8_t Last)
{
    uint8_t Index,Value,Error=0,Temp=0;
    FastI2C_Clock Clocks[9];
    uint32_t Previous;
    uint32_t Scl=FAST_SCL_PINS(Bus),Sda=FAST_SDA_PINS(Bus);
    uint32_t Edge=0,Saved=FastPort_Lock();
    for (Index=0;Index<8u;Index++) {
        Previous=ActualFallCycle;
        Error=Bit(Scl,Sda,1,&Value,&Edge);
        Clocks[Index].Period=ActualFallCycle-Previous;
        Clocks[Index].LowObserved=Edge-Previous;
        if (Error) { break; }
        Temp=(uint8_t)((Temp<<1)|Value);
    }
    if (!Error) {
        Previous=ActualFallCycle;
        Error=Bit(Scl,Sda,Last?1u:0u,&Value,&Edge);
        Clocks[8].Period=ActualFallCycle-Previous;
        Clocks[8].LowObserved=Edge-Previous;
    }
    FastPort_Unlock(Saved);
    if (!Error) {
        *Byte=Temp; memcpy((void *)LastByteClocks[Bus],Clocks,sizeof(Clocks));
    }
    return Error;
}
static uint8_t Begin(uint8_t Bus,uint8_t Address,FastI2C_Result *Result)
{
    uint8_t Error;
    memset(Result,0,sizeof(*Result));
    if (!Ready) { return I2C_CLOCK_ERROR; }
    if (Bus>1u || Address>0x7fu) { return I2C_BAD_ARGUMENT; }
    if ((FastPort_Read()&(FAST_SCL_PINS(Bus)|FAST_SDA_PINS(Bus))) !=
        (FAST_SCL_PINS(Bus)|FAST_SDA_PINS(Bus))) { return I2C_BUS_BUSY; }
    FallCycle=FastPort_Now();
    Error=Start(Bus,0);
    if (!Error) { Error=Send(Bus,(uint8_t)(Address<<1),1,Result); }
    return Error;
}
static uint8_t Finish(uint8_t Bus,uint8_t Error,FastI2C_Result *Result)
{
    uint8_t StopError;
    if (Bus<2u && Error!=I2C_CLOCK_ERROR && Error!=I2C_BAD_ARGUMENT) {
        StopError=Stop(Bus);
        if (!Error) { Error=StopError; }
    }
    Result->Status=Error;
    Result->EndCycle=FastPort_Now();
    return Error;
}
uint8_t FastI2C_Init(void)
{
    uint8_t Bus,Clock;
    uint32_t RiseCycle;
    Ready=FastPort_Init();
    if (!Ready) { return I2C_CLOCK_ERROR; }
    /* MCU在从机ACK时复位后可能残留SDA低，有限补钟和STOP恢复。
     * SCL本身低则不尝试强推高；每一路恢复有上限，不能拖死另一条总线。
     */
    for (Bus=0;Bus<2u;Bus++) {
        FastPort_Release(Bus);
        if (!(FastPort_Read()&FAST_SCL_PINS(Bus))) { continue; }
        if (FastPort_Read()&FAST_SDA_PINS(Bus)) { continue; }
        for (Clock=0;Clock<9u;Clock++) {
            Fall(Bus); FastPort_DelayUs(5);
            if (Rise(FAST_SCL_PINS(Bus),&RiseCycle)) { break; }
            FastPort_DelayUs(5);
            if (FastPort_Read()&FAST_SDA_PINS(Bus)) { break; }
        }
        (void)Stop(Bus);
    }
    return I2C_OK;
}
uint8_t FastI2C_Probe(uint8_t Bus,uint8_t Address,FastI2C_Result *Result)
{
    uint8_t Error;
    if (!Result) { return I2C_BAD_ARGUMENT; }
    Error=Begin(Bus,Address,Result);
    return Finish(Bus,Error,Result);
}
uint8_t FastI2C_WriteReg(uint8_t Bus,uint8_t Address,uint8_t Reg,
                         uint8_t Value,FastI2C_Result *Result)
{
    uint8_t Error;
    if (!Result) { return I2C_BAD_ARGUMENT; }
    Error=Begin(Bus,Address,Result);
    if (!Error) { Error=Send(Bus,Reg,0,Result); }
    if (!Error) { Error=Send(Bus,Value,0,Result); }
    return Finish(Bus,Error,Result);
}
uint8_t FastI2C_ReadRegs(uint8_t Bus,uint8_t Address,uint8_t Reg,
                         uint8_t *Data,uint8_t Count,FastI2C_Result *Result)
{
    uint8_t Error,Index;
    uint8_t Temp[14];
    if (!Result) { return I2C_BAD_ARGUMENT; }
    if (!Data || Count==0u || Count>14u) {
        memset(Result,0,sizeof(*Result)); Result->Status=I2C_BAD_ARGUMENT;
        return I2C_BAD_ARGUMENT;
    }
    Error=Begin(Bus,Address,Result);
    if (!Error) { Error=Send(Bus,Reg,0,Result); }
    if (!Error) { Error=Start(Bus,1); }
    if (!Error) { Error=Send(Bus,(uint8_t)((Address<<1)|1u),1,Result); }
    for (Index=0;Index<Count && !Error;Index++) {
        Error=Receive(Bus,&Temp[Index],(Index==Count-1u));
        if (!Error) { Result->Count++; }
    }
    Error=Finish(Bus,Error,Result);
    /* 包括STOP也成功才提交新数据，失败时保留调用者原内容并用状态明确无效。 */
    if (!Error) { memcpy(Data,Temp,Count); }
    return Error;
}
