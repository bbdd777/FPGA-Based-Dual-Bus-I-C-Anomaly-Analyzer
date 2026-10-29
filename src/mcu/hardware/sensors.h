#ifndef SENSORS_H
#define SENSORS_H
#include "fasti2c.h"

/* A为MPU6050(WHO=68)，B为MPU6500(WHO=70)，两条物理总线均地址68。
 * Data[0..13]来自3B..48；温度算法两器件不同，不混用6050换算公式。
 */
typedef struct {
    uint8_t Ready,Identity,Status,Reserved;
} Sensor_Info;
typedef struct {
    uint8_t Valid;
    uint8_t Raw[14];
    int16_t AX,AY,AZ,TemperatureRaw,GX,GY,GZ;
} Sensor_Data;
void Sensors_Reset(void);
uint8_t Sensors_Prepare(uint8_t Bus);
uint8_t Sensors_Read(uint8_t Bus,Sensor_Data *Data,FastI2C_Result *Result);
const Sensor_Info *Sensors_Info(uint8_t Bus);
#endif
