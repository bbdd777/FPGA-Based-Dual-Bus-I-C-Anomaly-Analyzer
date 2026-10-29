#ifndef __TIMER_H
#define __TIMER_H

#include "stm32f10x.h"

void Timer_Init(void);
uint32_t Timer_GetTick(void);               // 单位ms，约49.7天后自然绕回

#endif
