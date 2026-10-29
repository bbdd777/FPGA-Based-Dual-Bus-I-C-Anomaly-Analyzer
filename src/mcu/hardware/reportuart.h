#ifndef REPORT_UART_H
#define REPORT_UART_H
#include "failoverapp.h"
void ReportUart_Init(void);
void ReportUart_Send(const volatile Failover_Report *Report);
#endif
