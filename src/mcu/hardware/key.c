#include "stm32f10x.h"                  // Device header
#include "key.h"

#define KEY_DEBOUNCE_MS    20

static volatile uint8_t Key_Num;            // 中断写、主循环读的一次按下事件
static uint8_t Key_LastRead;
static uint8_t Key_StableState;
static uint8_t Key_Count;

void Key_Init(void)
{
    GPIO_InitTypeDef GPIO_InitStructure;

    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOB, ENABLE);
    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IPD;
    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_12;
    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(GPIOB, &GPIO_InitStructure);
    // 沿用模板：PB12内部下拉，按键另一端接3.3V，按下读到1。
    Key_Num = 0;
    Key_LastRead = 0;
    Key_StableState = 0;
    Key_Count = 0;
}

uint8_t Key_GetNum(void)
{
    uint8_t Temp;
    uint32_t Primask;

    // 读事件和清零放在一起，防止两句之间恰好发生中断而丢失新事件。
    Primask = __get_PRIMASK();
    __disable_irq();
    Temp = Key_Num;
    Key_Num = 0;
    __set_PRIMASK(Primask);
    return Temp;
}

void Key_Tick(void)
{
    uint8_t ReadState;

    ReadState = GPIO_ReadInputDataBit(GPIOB, GPIO_Pin_12);
    if (ReadState != Key_LastRead)
    {
        Key_LastRead = ReadState;
        Key_Count = 1;                     // 电平改变，从当前采样重新计数
    }
    else if (Key_Count < KEY_DEBOUNCE_MS)
    {
        Key_Count++;
    }
    if (Key_Count >= KEY_DEBOUNCE_MS && ReadState != Key_StableState)
    {
        Key_StableState = ReadState;        // 连续20个1ms采样一致才认可变化
        if (Key_StableState != 0)
        {
            Key_Num = 1;                   // 稳定按下产生一次事件，长按不连发
        }
    }
}
