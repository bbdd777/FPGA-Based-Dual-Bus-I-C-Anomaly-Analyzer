#include "stm32f10x.h"
#include "oled.h"
#include "key.h"
#include "timer.h"
#include "failoverapp.h"
#include "reportuart.h"

/* PB12按键只在M0/M1/M2/M3间循环。上电空闲，不初始化/读取传感器。
 * M1是双路正常自检；M2/M3只把B作为故障后的有效备用数据源。
 * 每5秒发起一轮，方便FPGA上传后再次取证。UART输出与OLED都在事务后进行。
 */
#define APP_REPEAT_MS 5000u
volatile uint8_t Mode=0;
volatile uint8_t StartupStatus=0;
static void Show(void)
{
    OLED_Clear(); OLED_ShowString(1,1,"MCU4 M:"); OLED_ShowNum(1,8,Mode,1);
    OLED_ShowString(1,10,"400k");
    OLED_ShowString(2,1,(char *)Failover_Name(Mode));
    OLED_ShowString(3,1,"A:   B:   S:");
    OLED_ShowNum(3,3,LastReport.AResult.Status,2);
    OLED_ShowNum(3,8,LastReport.BResult.Status,2);
    OLED_ShowChar(3,13,LastReport.Source==2u?'B':(LastReport.Source==1u?'A':'-'));
    OLED_ShowString(4,1,"V:  ACKus:");
    OLED_ShowNum(4,3,LastReport.BData.Valid,1);
    OLED_ShowNum(4,11,LastReport.BackupAckUs,5);
}
/* 自动取证只在本函数返回后的空闲点读LastReport；不得暂停在I2C位中间。 */
void App_RunOnce(uint8_t Selected)
{
    if (Failover_Run(Selected)) { ReportUart_Send(&LastReport); Show(); }
}
int main(void)
{
    uint32_t LastRun;
    OLED_Init(); Key_Init(); Timer_Init();
    StartupStatus=Failover_Init(); ReportUart_Init();
    App_RunOnce(0); LastRun=Timer_GetTick();
    while (1) {
        if (Key_GetNum()==1u) {
            Mode=(uint8_t)((Mode+1u)%APP_MODE_COUNT);
            App_RunOnce(Mode); LastRun=Timer_GetTick();
        } else if (Mode && (uint32_t)(Timer_GetTick()-LastRun)>=APP_REPEAT_MS) {
            App_RunOnce(Mode); LastRun=Timer_GetTick();
        }
    }
}
