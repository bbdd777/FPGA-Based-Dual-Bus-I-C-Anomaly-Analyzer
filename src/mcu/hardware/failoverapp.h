#ifndef FAILOVER_APP_H
#define FAILOVER_APP_H
#include "sensors.h"
#define APP_MODE_COUNT 4u
#define APP_LOG_DEPTH 16u
#define APP_SOURCE_NONE 0u
#define APP_SOURCE_A 1u
#define APP_SOURCE_B 2u
#define APP_FAULT_NONE 0u
#define APP_FAULT_A_NACK 1u
#define APP_FAULT_A_SCL 2u
#define APP_FAULT_A_OTHER 3u
typedef struct {
    uint32_t Sequence;
    uint8_t Mode,Active,Fault,Source;
    uint8_t BackupAttempted,BackupSuccess,BackupAckValid,WithinWindow;
    uint32_t FaultCycle,BackupAckUs,BackupReadUs,LowHoldUs;
    FastI2C_Result AResult,BResult;
    Sensor_Data AData,BData;
} Failover_Report;
extern volatile Failover_Report LastReport;
extern volatile Failover_Report EventLog[APP_LOG_DEPTH];
extern volatile uint32_t EventLogCount;
uint8_t Failover_Init(void);
/* 同步执行一轮，初始化最多约200ms，已初始化普通读取约亚毫秒级。
 * 非可重入；只允许主循环调用，不能放入中断。Mode越界不执行。
 * M0保留历史日志，但清当前数据有效标志，四路开漏输出释放。
 */
uint8_t Failover_Run(uint8_t Mode);
const char *Failover_Name(uint8_t Mode);
#endif
