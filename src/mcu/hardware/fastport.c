#include "fastport.h"

#ifdef MCU_HOST_TEST
void FastPort_WaitUntil(uint32_t Deadline)
{
    while ((int32_t)(FastPort_Now()-Deadline)<0) { }
}
#endif
void FastPort_DelayUs(uint32_t Us)
{
    FastPort_WaitUntil(FastPort_Now()+Us*FAST_CYCLES_US);
}
void FastPort_Release(uint8_t Bus)
{
    FastPort_Set(FAST_SCL_PINS(Bus)|FAST_SDA_PINS(Bus));
}
void FastPort_HoldALow(uint8_t Hold)
{
    FastPort_Set(FAST_SDA_PINS(0));
    if (Hold) { FastPort_Clear(FAST_SCL_PINS(0)); }
    else { FastPort_Set(FAST_SCL_PINS(0)); }
}

#ifndef MCU_HOST_TEST
uint8_t FastPort_Init(void)
{
    GPIO_InitTypeDef Init;
    uint32_t First;
    uint8_t Index;
    /* 项目启动文件配置72MHz；若移植后不匹配，拒绝假装400kHz运行。 */
    SystemCoreClockUpdate();
    if (SystemCoreClock!=FAST_CORE_HZ) { return 0; }
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    FAST_DWT_CTRL |= 1u;
    First=FastPort_Now();
    for (Index=0;Index<32u;Index++) { __NOP(); }
    if (First==FastPort_Now()) { return 0; }
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOB,ENABLE);
    FastPort_Set((1u<<10)|(1u<<11)|(1u<<13)|(1u<<14));
    Init.GPIO_Pin=(1u<<10)|(1u<<11)|(1u<<13)|(1u<<14);
    Init.GPIO_Mode=GPIO_Mode_Out_OD;
    Init.GPIO_Speed=GPIO_Speed_50MHz;
    GPIO_Init(GPIOB,&Init);
    return 1;
}
#endif
