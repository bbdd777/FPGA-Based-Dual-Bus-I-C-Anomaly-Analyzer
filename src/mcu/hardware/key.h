#ifndef __KEY_H
#define __KEY_H

#include "stm32f10x.h"

void Key_Init(void);
uint8_t Key_GetNum(void);
void Key_Tick(void);                        // 由TIM2每1ms调用一次

#endif
