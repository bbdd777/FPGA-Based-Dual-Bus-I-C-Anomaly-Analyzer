#ifndef FAST_I2C_H
#define FAST_I2C_H
#include <stdint.h>

/* 四模式工程的总线接口。Bus=0为A，Bus=1为B；地址均是7位地址。
 * 所有函数有界返回，不发送假ACK。0表示成功，未执行和失败不产生有效数据。
 * 同步调用：一次只操作一条总线；M1依次读取两路，不声称两路重叠。
 */
#define BUS_A 0u
#define BUS_B 1u
#define I2C_OK 0u
#define I2C_NOT_RUN 1u
#define I2C_BUS_BUSY 2u
#define I2C_SCL_TIMEOUT 3u
#define I2C_ADDRESS_NACK 4u
#define I2C_DATA_NACK 5u
#define I2C_BAD_ARGUMENT 6u
#define I2C_CLOCK_ERROR 7u
#define I2C_ID_ERROR 8u
#define I2C_CONFIG_ERROR 9u
#define I2C_INJECTED_LOW 10u

typedef struct {
    uint8_t Status;          /* 最先发生的错误，STOP失败也保留最初错误。 */
    uint8_t AddressValid;    /* 地址第9位真的采样过才为1。 */
    uint8_t AddressNack;     /* AddressValid=1时才解释：0 ACK、1 NACK。 */
    uint8_t Count;           /* 实际读取字节数，Status=0且Count符合才算完整。 */
    uint32_t AddressCycle;  /* 首个地址第9位观察到SCL高的DWT周期编号。 */
    uint32_t EndCycle;      /* STOP/错误退出后周期编号。 */
} FastI2C_Result;
/* 每路最近一个字节9个时钟的MCU周期观测，用于上板核对软件命令节拍。
 * [0]可能含字节间低电平间隙；[1..8]用于稳态检查。
 * LowObserved包含GPIO读高观测延迟；不能替代示波器的电压门限测量。
 */
typedef struct { uint32_t Period,LowObserved; } FastI2C_Clock;
extern volatile FastI2C_Clock LastByteClocks[2][9];

uint8_t FastI2C_Init(void);
uint8_t FastI2C_Probe(uint8_t Bus, uint8_t Address, FastI2C_Result *Result);
uint8_t FastI2C_WriteReg(uint8_t Bus, uint8_t Address, uint8_t Reg,
                         uint8_t Value, FastI2C_Result *Result);
uint8_t FastI2C_ReadRegs(uint8_t Bus, uint8_t Address, uint8_t Reg,
                         uint8_t *Data, uint8_t Count, FastI2C_Result *Result);
#endif
