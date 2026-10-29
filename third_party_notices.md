# 第三方来源与原声明

本文件登记提交副本中已经识别的第三方组成、外部依赖及来源状态。原文件内版权和使用声明保持不变；本项目不据此替第三方选择或授予新的开源协议。

## 随 MCU 工程保留的原厂支持文件

| 组成 | 包内位置 | 已核实来源与原声明 |
|---|---|---|
| STM32F10x 标准外设库 | `src/mcu/library/` | 文件头标记 STMicroelectronics、MCD Application Team；所读 GPIO 文件为 V3.5.0、2011-03-11，保留 ST 原声明 |
| STM32 启动与器件支持 | `src/mcu/start/startup_stm32f10x_*.s`、`stm32f10x.h`、`system_stm32f10x.*` | 保留各文件原厂来源、版本及原声明；中密度启动文件标记 ST V3.5.0、2011-03-11 |
| ARM CMSIS Cortex-M3 核心层 | `src/mcu/start/core_cm3.h` 等原支持文件 | 已读头文件为 V1.30、2009-10-30，版权 ARM Limited；文件头载明相应用途及分发条款，原文留在文件中 |
| 既有 OLED 驱动和字模 | `src/mcu/hardware/oled.c`、`oled.h`、`oled_font.h` | 沿用既有工程；已检查的文件头未给出足以确认上游出处和独立授权的声明，来源和再分发依据需由提交者补核 |

该表只描述核实结果，不将旧版 ST 或 ARM 文件重标为 MIT、BSD 或其他当前常见协议。需要完整许可文本时，应取得所用原版本配套文件并核对，不能用新版库的许可替代旧文件原声明。

## 外部 Python 依赖

直接依赖为 pyserial 与 Matplotlib，固定版本及传递依赖见 `src/pc/requirements-lock.txt`，其中包括 NumPy、Pillow、contourpy、cycler、fonttools、kiwisolver、packaging、pyparsing、python-dateutil 和 six。

依赖通过安装器单独获取，使用条款、版权与依赖声明以对应版本发行包为准。锁文件记录版本，不替代这些原声明。Python、Tk/Tcl 与系统字体由运行环境提供，不以本工程自有代码名义重新授权。

## 构建工具、驱动和设备资料

Vivado、Keil MDK、ARMCC/fromelf、ST-Link、USB 串口驱动及其支持软件由各自提供方分发，本包仅记录构建入口和环境要求，不包含工具安装目录或替它们授予使用权。运行者根据实际工具安装提供路径。

I2C 规范、AMD/Xilinx 文档和 MPU6050/MPU6500 资料在报告中作来源引用。说明性示意图与由本项目测试数据绘制的波形须按图题区分；原厂手册和教材不作为本项目原创资料重新发布。

## 项目自有部分

FPGA 逻辑、项目应用代码、报告、测试数据及 Skill 等材料的最终权利人与发布协议，需要在对外发布前确认。当前材料中若有上游文件原声明，其权利归属继续按原文件处理。本文件没有创建项目 LICENSE，也不意味着第三方来源核验已经全部完成。
