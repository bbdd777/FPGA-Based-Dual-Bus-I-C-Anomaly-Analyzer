#include "stm32f10x.h"                  // Device header
#include "timer.h"
#include "key.h"

static volatile uint32_t Timer_Ms;

void Timer_Init(void)
{
    TIM_TimeBaseInitTypeDef TIM_TimeBaseInitStructure;
    NVIC_InitTypeDef NVIC_InitStructure;

    RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM2, ENABLE);
    TIM_InternalClockConfig(TIM2);
    // 模板系统时钟72MHz，APB1分频为2，TIM2仍得到72MHz定时器时钟。
    // 72MHz / 7200 / 10 = 1000Hz，因此每1ms进入一次更新中断。
    TIM_TimeBaseInitStructure.TIM_ClockDivision = TIM_CKD_DIV1; // 不参与计数分频
    TIM_TimeBaseInitStructure.TIM_CounterMode = TIM_CounterMode_Up;
    TIM_TimeBaseInitStructure.TIM_Period = 10 - 1;
    TIM_TimeBaseInitStructure.TIM_Prescaler = 7200 - 1;
    TIM_TimeBaseInitStructure.TIM_RepetitionCounter = 0;
    TIM_TimeBaseInit(TIM2, &TIM_TimeBaseInitStructure);
    TIM_ClearITPendingBit(TIM2, TIM_IT_Update); // 初始化会产生更新，启动前清掉
    TIM_ITConfig(TIM2, TIM_IT_Update, ENABLE);

    NVIC_PriorityGroupConfig(NVIC_PriorityGroup_2);
    NVIC_InitStructure.NVIC_IRQChannel = TIM2_IRQn;
    NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;
    NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 2;
    NVIC_InitStructure.NVIC_IRQChannelSubPriority = 1;
    NVIC_Init(&NVIC_InitStructure);
    Timer_Ms = 0;
    TIM_Cmd(TIM2, ENABLE);
}

uint32_t Timer_GetTick(void)
{
    // Cortex-M3对齐的32位读取一次完成；volatile保证读取中断更新后的值。
    return Timer_Ms;
}

void TIM2_IRQHandler(void)
{
    if (TIM_GetITStatus(TIM2, TIM_IT_Update) == SET)
    {
        TIM_ClearITPendingBit(TIM2, TIM_IT_Update);
        Timer_Ms++;
        Key_Tick();
        // 中断不读取MPU、不刷新OLED、不调用Delay，避免两处同时操作SysTick。
    }
}
