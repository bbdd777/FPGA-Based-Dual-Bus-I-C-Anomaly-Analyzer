#include "sensors.h"
#include "fastport.h"
#include <string.h>
static Sensor_Info Info[2];
static const uint8_t ExpectedId[2]={0x68u,0x70u};
/* ±2g、±250deg/s；19=9，DLPF=3。6500加速度滤波单独设1D=3。 */
static const uint8_t ConfigRegs[]={0x6bu,0x6cu,0x1au,0x19u,0x1bu,0x1cu};
static const uint8_t ConfigValues[]={0x01u,0x00u,0x03u,0x09u,0x00u,0x00u};
void Sensors_Reset(void) { memset(Info,0,sizeof(Info)); }
const Sensor_Info *Sensors_Info(uint8_t Bus) { return Bus<2u?&Info[Bus]:0; }
uint8_t Sensors_Prepare(uint8_t Bus)
{
    FastI2C_Result Result;
    uint8_t Value=0,Index,Status;
    if (Bus>1u) { return I2C_BAD_ARGUMENT; }
    if (Info[Bus].Ready) { return I2C_OK; }
    Info[Bus].Identity=0;
    Status=FastI2C_ReadRegs(Bus,0x68u,0x75u,&Value,1,&Result);
    if (!Status) {
        Info[Bus].Identity=Value;
        if (Value!=ExpectedId[Bus]) { Status=I2C_ID_ERROR; }
    }
    for (Index=0;Index<sizeof(ConfigRegs) && !Status;Index++) {
        Status=FastI2C_WriteReg(Bus,0x68u,ConfigRegs[Index],ConfigValues[Index],&Result);
        if (Index==0u && !Status) { FastPort_DelayUs(100000u); }
        if (!Status) {
            Status=FastI2C_ReadRegs(Bus,0x68u,ConfigRegs[Index],&Value,1,&Result);
            if (!Status && Value!=ConfigValues[Index]) { Status=I2C_CONFIG_ERROR; }
        }
    }
    if (!Status && Bus==BUS_B) {
        Status=FastI2C_WriteReg(Bus,0x68u,0x1du,0x03u,&Result);
        if (!Status) { Status=FastI2C_ReadRegs(Bus,0x68u,0x1du,&Value,1,&Result); }
        if (!Status && Value!=0x03u) { Status=I2C_CONFIG_ERROR; }
    }
    Info[Bus].Status=Status;
    Info[Bus].Ready=(Status==I2C_OK);
    return Status;
}
static int16_t Word(const uint8_t *Bytes)
{
    return (int16_t)(((uint16_t)Bytes[0]<<8)|Bytes[1]);
}
uint8_t Sensors_Read(uint8_t Bus,Sensor_Data *Data,FastI2C_Result *Result)
{
    uint8_t Status;
    if (!Data || !Result) { return I2C_BAD_ARGUMENT; }
    memset(Data,0,sizeof(*Data));
    memset(Result,0,sizeof(*Result));
    if (Bus>1u) { Result->Status=I2C_BAD_ARGUMENT; return Result->Status; }
    if (!Info[Bus].Ready) {
        Result->Status=Info[Bus].Status?Info[Bus].Status:I2C_NOT_RUN;
        return Result->Status;
    }
    Status=FastI2C_ReadRegs(Bus,0x68u,0x3bu,Data->Raw,14,Result);
    if (Status || Result->Count!=14u) {
        Info[Bus].Ready=0;
        return Status;
    }
    Data->AX=Word(&Data->Raw[0]); Data->AY=Word(&Data->Raw[2]);
    Data->AZ=Word(&Data->Raw[4]); Data->TemperatureRaw=Word(&Data->Raw[6]);
    Data->GX=Word(&Data->Raw[8]); Data->GY=Word(&Data->Raw[10]);
    Data->GZ=Word(&Data->Raw[12]); Data->Valid=1;
    return I2C_OK;
}
