#ifndef FAST_PORT_H
#define FAST_PORT_H
#include <stdint.h>

/* 平台层：72MHz Cortex-M3周期编号，32位约59.65秒回绕。
 * 时间比较均用uint32_t模减；本工程最长等待500ms，小于半个回绕周期。
 * Write1=开漏释放，不是推挽输出高；板上必须有3.3V上拉。
 */
#define FAST_CORE_HZ 72000000u
#define FAST_CYCLES_US 72u
#define FAST_SCL_PINS(bus) ((bus)==0u ? (1u<<10) : (1u<<13))
#define FAST_SDA_PINS(bus) ((bus)==0u ? (1u<<11) : (1u<<14))

#ifdef MCU_HOST_TEST
#define FAST_INLINE static inline
uint32_t FastPort_Now(void);
void FastPort_Set(uint32_t Pins);
void FastPort_Clear(uint32_t Pins);
uint32_t FastPort_Read(void);
uint32_t FastPort_Lock(void);
void FastPort_Unlock(uint32_t Saved);
#else
#include "stm32f10x.h"
#define FAST_INLINE static __forceinline
/* 旧CMSIS头文件没有DWT结构体，使用ARM定义的控制/计数寄存器地址。 */
#define FAST_DWT_CTRL (*(volatile uint32_t *)0xE0001000u)
#define FAST_DWT_CYCCNT (*(volatile uint32_t *)0xE0001004u)
#define FastPort_Now() (FAST_DWT_CYCCNT)
#define FastPort_Set(pins) (GPIOB->BSRR=(pins))
#define FastPort_Clear(pins) (GPIOB->BRR=(pins))
#define FastPort_Read() (GPIOB->IDR)
#define FastPort_Lock() FastPort_LockImpl()
#define FastPort_Unlock(saved) __set_PRIMASK(saved)
FAST_INLINE void FastPort_WaitUntil(uint32_t Deadline)
{
    /* 直接判断模差最高位，并保留NOP，避免旧ARMCC对空循环过度优化。
     * 仍须在每次正式构建后检查反汇编存在计数重读和回跳。
     */
    while ((FastPort_Now()-Deadline)&0x80000000u) { __NOP(); }
}
static __inline uint32_t FastPort_LockImpl(void)
{
    uint32_t Saved=__get_PRIMASK();
    __disable_irq();
    return Saved;
}
#endif

uint8_t FastPort_Init(void);
#ifdef MCU_HOST_TEST
void FastPort_WaitUntil(uint32_t Deadline);
#endif
void FastPort_DelayUs(uint32_t Us);
void FastPort_Release(uint8_t Bus);
/* 仅故障注入调用：先释放SDA，再拉低A_SCL；B不受影响。 */
void FastPort_HoldALow(uint8_t Hold);
#endif
