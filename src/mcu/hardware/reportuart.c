#ifndef MCU_HOST_TEST
#include "stm32f10x.h"
#endif
#include "reportuart.h"
#include "fastport.h"

/* 独立MCU结果口：PA9 TX，115200/8N1，只发送不接收。
 * 不接FPGA的TX，不改变FPGA格式03。需要电脑接收时接3.3V USB-TTL RX与共地。
 * 串口只在本轮I2C结束后发送，绝不在400kHz位时序中输出文本。
 */
static uint8_t Check,Failed;
#ifdef MCU_HOST_TEST
extern void TestUart_Char(char Value);
void ReportUart_Init(void) { }
static void Raw(char Value) { TestUart_Char(Value); }
#else
void ReportUart_Init(void)
{
    GPIO_InitTypeDef Init;
    RCC_ClocksTypeDef Clocks;
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA|RCC_APB2Periph_USART1,ENABLE);
    GPIO_SetBits(GPIOA,GPIO_Pin_9);
    Init.GPIO_Pin=GPIO_Pin_9; Init.GPIO_Mode=GPIO_Mode_AF_PP;
    Init.GPIO_Speed=GPIO_Speed_50MHz; GPIO_Init(GPIOA,&Init);
    RCC_GetClocksFreq(&Clocks);
    USART1->BRR=(Clocks.PCLK2_Frequency+57600u)/115200u;
    USART1->CR1=USART_CR1_UE|USART_CR1_TE;
}
static void Raw(char Value)
{
    uint32_t Start=FastPort_Now();
    uint32_t Attempts=0;
    while (!(USART1->SR&USART_SR_TXE)) {
        if (FastPort_Now()-Start>2000u*FAST_CYCLES_US || ++Attempts>200000u) {
            Failed=1; return;
        }
    }
    if (!Failed) { USART1->DR=(uint8_t)Value; }
}
#endif
static void Put(char Value) { Check^=(uint8_t)Value; Raw(Value); }
static void Text(const char *Value) { while (*Value) { Put(*Value++); } }
static void Number(uint32_t Value)
{
    char Digits[10]; uint8_t Count=0;
    do { Digits[Count++]=(char)('0'+Value%10u); Value/=10u; } while (Value);
    while (Count) { Put(Digits[--Count]); }
}
static char Hex(uint8_t Value) { return "0123456789ABCDEF"[Value&15u]; }
static void Field(uint32_t Value) { Put(','); Number(Value); }
void ReportUart_Send(const volatile Failover_Report *R)
{
    uint8_t Index,Sum;
    Check=0; Failed=0; Raw('$'); Text("MCU4,1");
    Field(R->Sequence); Field(R->Mode); Field(R->Fault); Field(R->Source);
    Field(R->AResult.Status); Field(R->BResult.Status);
    Field(R->AData.Valid); Field(R->BData.Valid); Field(R->BackupAttempted);
    Field(R->BackupSuccess); Field(R->BackupAckValid); Field(R->WithinWindow);
    Field(R->BackupAckUs); Field(R->BackupReadUs); Field(R->LowHoldUs);
    Put(',');
    for (Index=0;Index<14u;Index++) { Put(Hex(R->AData.Raw[Index]>>4)); Put(Hex(R->AData.Raw[Index])); }
    Put(',');
    for (Index=0;Index<14u;Index++) { Put(Hex(R->BData.Raw[Index]>>4)); Put(Hex(R->BData.Raw[Index])); }
    Sum=Check; Raw('*'); Raw(Hex(Sum>>4)); Raw(Hex(Sum)); Raw('\r'); Raw('\n');
}
